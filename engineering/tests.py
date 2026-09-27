"""Isolation, boundedness, HTTP and outbox transaction regression tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.contrib.auth.models import AnonymousUser, Group, User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import close_old_connections, connection, DatabaseError, IntegrityError, transaction
from django.http import Http404
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Domes.ratelimits import _client_ip_identity
from . import services
from .forms import SubmissionForm
from .models import ConsumerReceipt, LabRun, OutboxEvent, Submission, Trace

PREDICTION = {"status": "uncertain", "label": None, "score": 0.4, "terms": [], "version": "test", "latency_ms": 0.1}


def new_run(owner="a", slot=0):
    return LabRun.objects.create(owner_hash=owner * 64, slot=slot, expires_at=timezone.now() + timedelta(hours=24))


def new_submission(run, key=None, text="The export button returns an error."):
    return services.submit(run, key or uuid.uuid4(), text, PREDICTION)[0]


def preloaded_session_requests(count):
    session = SessionStore()
    session["unrelated"] = "preserved"
    session.create()
    requests = []
    for _ in range(count):
        request = RequestFactory().post("/engineering/runs/")
        request.user = AnonymousUser()
        request.session = SessionStore(session_key=session.session_key)
        assert request.session.get("unrelated") == "preserved"
        requests.append(request)
    return session.session_key, requests


class LabOwnerInitializationTests(TestCase):
    def test_independently_preloaded_sessions_converge_without_stranding_runs(self):
        session_key, requests = preloaded_session_requests(4)
        runs = [services.create_run(request) for request in requests[:3]]
        with self.assertRaises(services.LabCapacity):
            services.create_run(requests[3])
        for request in reversed(requests):
            request.session.save()
        final_request = RequestFactory().get("/")
        final_request.user = AnonymousUser()
        final_request.session = SessionStore(session_key=session_key)
        self.assertEqual(final_request.session["unrelated"], "preserved")
        self.assertEqual(len({run.owner_hash for run in runs}), 1)
        self.assertEqual(LabRun.objects.count(), 3)
        for run in runs:
            self.assertEqual(services.owned_run(final_request, run.pk), run)

    def test_deleted_or_expired_preloaded_session_is_not_resurrected(self):
        for expired in [False, True]:
            with self.subTest(expired=expired):
                session_key, requests = preloaded_session_requests(1)
                query = Session.objects.filter(session_key=session_key)
                if expired:
                    query.update(expire_date=timezone.now() - timedelta(seconds=1))
                else:
                    query.delete()
                with self.assertRaises(Http404):
                    services.create_run(requests[0])
                self.assertEqual(LabRun.objects.count(), 0)
                if expired:
                    self.assertLess(Session.objects.get(pk=session_key).expire_date, timezone.now())
                else:
                    self.assertFalse(Session.objects.filter(pk=session_key).exists())


class LabServiceTests(TestCase):
    def setUp(self):
        self.run = new_run()

    def test_same_key_returns_original_and_changed_payload_conflicts(self):
        key = uuid.uuid4()
        first, created = services.submit(self.run, key, "A broken export\r\nbutton", PREDICTION)
        self.assertTrue(created)
        second, created = services.submit(self.run, key, "A broken export\nbutton", {})
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.triage, PREDICTION)
        with self.assertRaises(services.LabConflict):
            services.submit(self.run, key, "A different payload", PREDICTION)
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)
        self.assertTrue(Trace.objects.filter(stage="replay_conflict").exists())

    def test_event_failure_rolls_back_submission_and_trace(self):
        with patch("engineering.services.OutboxEvent.objects.create", side_effect=IntegrityError("injected")):
            with self.assertRaises(IntegrityError):
                new_submission(self.run)
        self.assertEqual(Submission.objects.count(), 0)
        self.assertEqual(Trace.objects.count(), 0)

    def test_ten_submissions_and_eighty_traces_are_hard_caps(self):
        first = new_submission(self.run)
        for _ in range(9):
            new_submission(self.run)
        with self.assertRaises(services.LabCapacity):
            new_submission(self.run)
        for _ in range(90):
            services.submit(self.run, first.idempotency_key, first.text, {})
        self.assertEqual(Submission.objects.count(), 10)
        self.assertEqual(Trace.objects.count(), 80)

    def test_five_attempts_are_limit_and_receipt_is_unique(self):
        submission = new_submission(self.run)
        for _ in range(5):
            claim = services.claim_delivery(self.run, submission.event.id, "lost_ack")
            services.commit_receipt(claim)
            services.finish_attempt(claim, "lost_ack")
        with self.assertRaises(services.LabCapacity):
            services.claim_delivery(self.run, submission.event.id, "success")
        event = OutboxEvent.objects.get(pk=submission.event.id)
        self.assertEqual(event.attempt_count, 5)
        self.assertEqual(event.status, "exhausted")
        self.assertEqual(ConsumerReceipt.objects.count(), 1)

    def test_live_lease_rejects_another_attempt(self):
        submission = new_submission(self.run)
        claim = services.claim_delivery(self.run, submission.event.id, "success")
        with self.assertRaises(services.AttemptBusy):
            services.claim_delivery(self.run, submission.event.id, "success")
        self.assertEqual(OutboxEvent.objects.get(pk=claim.event_id).claim_token, claim.token)

    def test_stale_attempt_cannot_release_or_acknowledge_replacement(self):
        submission = new_submission(self.run)
        first = services.claim_delivery(self.run, submission.event.id, "lost_ack")
        services.commit_receipt(first)
        OutboxEvent.objects.filter(pk=first.event_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        second = services.claim_delivery(self.run, submission.event.id, "success")
        self.assertEqual(services.finish_attempt(first, "lost_ack"), "stale")
        self.assertEqual(OutboxEvent.objects.get(pk=first.event_id).claim_token, second.token)
        self.assertEqual(services.commit_receipt(second), "duplicate_prevented")
        self.assertEqual(services.finish_attempt(second, "acknowledged"), "acknowledged")
        self.assertEqual(services.finish_attempt(first, "lost_ack"), "stale")
        self.assertEqual(OutboxEvent.objects.get(pk=first.event_id).status, "delivered")
        self.assertEqual(ConsumerReceipt.objects.count(), 1)

    def test_expired_claim_cannot_write_destination_without_reclaim(self):
        submission = new_submission(self.run)
        claim = services.claim_delivery(self.run, submission.event.id, "success")
        OutboxEvent.objects.filter(pk=claim.event_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(services.commit_receipt(claim), "stale")
        self.assertEqual(ConsumerReceipt.objects.count(), 0)

    def test_foreign_event_and_expired_run_rejected(self):
        second = new_run("b")
        submission = new_submission(second)
        with self.assertRaises(Http404):
            services.claim_delivery(self.run, submission.event.id, "success")
        LabRun.objects.filter(pk=self.run.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(Http404):
            new_submission(self.run)

    def test_no_acknowledgement_without_receipt(self):
        submission = new_submission(self.run)
        claim = services.claim_delivery(self.run, submission.event.id, "success")
        with self.assertRaises(services.LabConflict):
            services.finish_attempt(claim, "acknowledged")
        self.assertEqual(OutboxEvent.objects.get(pk=claim.event_id).status, "processing")

    def test_run_that_expires_during_lock_wait_cannot_accept_a_write(self):
        before = timezone.now()
        self.run.expires_at = before + timedelta(seconds=1)
        with patch("engineering.services.timezone.now", return_value=before) as clock:
            def acquire_lock(*args, **kwargs):
                clock.return_value = before + timedelta(seconds=2)
                return self.run
            with patch("engineering.services.LabRun.objects.select_for_update") as queryset:
                queryset.return_value.get.side_effect = acquire_lock
                with self.assertRaises(Http404):
                    services._lock_run(self.run.id)

    def test_cleanup_is_bounded_and_cascades_only_expired_roots(self):
        for owner in ["b", "c", "d"]:
            expired = new_run(owner)
            new_submission(expired)
            LabRun.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        output = StringIO()
        call_command("cleanup_engineering_runs", batch_size=1, max_batches=2, stdout=output)
        self.assertIn("Purged 2", output.getvalue())
        self.assertEqual(LabRun.objects.count(), 2)
        self.assertTrue(LabRun.objects.filter(pk=self.run.pk).exists())
        self.assertEqual(Submission.objects.count(), 1)

    def test_invalid_cleanup_bounds_and_unknown_transport_rejected(self):
        with self.assertRaises(ValueError):
            services.purge_expired_runs(batch_size=100000)
        with self.assertRaises(ValueError):
            services.claim_delivery(self.run, uuid.uuid4(), "https://example.com")

    def test_existing_daily_demo_reset_also_purges_expired_runs(self):
        expired = new_run("e")
        LabRun.objects.filter(pk=expired.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        call_command("reset_demo_sandbox", stdout=StringIO())
        self.assertFalse(LabRun.objects.filter(pk=expired.pk).exists())
        self.assertTrue(LabRun.objects.filter(pk=self.run.pk).exists())

    def test_text_form_bounds_and_control_characters(self):
        for text in ["xx", "x" * 1501, "\u0344" * 751, "hello\x00world", "hidden\u202etext"]:
            self.assertFalse(SubmissionForm({"text": text, "idempotency_key": uuid.uuid4()}).is_valid())
        form = SubmissionForm({"text": "<script>alert(1)</script>", "idempotency_key": uuid.uuid4()})
        self.assertTrue(form.is_valid())  # Always rendered as escaped plain text.

    def test_database_rejects_impossible_claim_and_extra_owner_slot(self):
        submission = new_submission(self.run)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OutboxEvent.objects.filter(pk=submission.event.id).update(status="processing")
        with self.assertRaises(IntegrityError), transaction.atomic():
            new_run("a", 3)


@override_settings(ENGINEERING_LAB_ENABLED=True)
class LabHttpTests(TransactionTestCase):
    def setUp(self):
        self.triage_patch = patch("engineering.views.triage.classify", return_value=PREDICTION)
        self.triage_patch.start()
        self.addCleanup(self.triage_patch.stop)

    def start(self, client=None):
        response = (client or self.client).post(reverse("engineering:create_run"))
        self.assertEqual(response.status_code, 303)
        return LabRun.objects.get(pk=response["Location"].strip("/").split("/")[-1])

    def post_submission(self, run, client=None, **overrides):
        data = {"text": "The export button returns an error.", "idempotency_key": uuid.uuid4()}
        data.update(overrides)
        return (client or self.client).post(reverse("engineering:submit", args=[run.id]), data)

    def test_complete_html_walkthrough_lost_ack_and_idempotent_replay(self):
        run = self.start()
        key = uuid.uuid4()
        self.assertEqual(self.post_submission(run, idempotency_key=key).status_code, 303)
        submission = Submission.objects.get(run=run)
        url = reverse("engineering:delivery", args=[run.id])
        self.assertEqual(self.client.post(url, {"event_id": submission.event.id, "scenario": "lost_ack"}).status_code, 303)
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.get().status, "retry")
        self.assertEqual(self.client.post(url, {"event_id": submission.event.id, "scenario": "success"}).status_code, 303)
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.get().status, "delivered")
        self.assertEqual(self.post_submission(run, idempotency_key=key).status_code, 303)
        self.assertEqual(Submission.objects.count(), 1)

    def test_failure_before_delivery_has_no_effect(self):
        run = self.start()
        self.post_submission(run)
        event = OutboxEvent.objects.get()
        self.client.post(reverse("engineering:delivery", args=[run.id]), {"event_id": event.id, "scenario": "fail_before_delivery"})
        self.assertEqual(ConsumerReceipt.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.get().status, "retry")

    def test_cross_session_get_submit_delivery_reset_are_404(self):
        run = self.start()
        self.post_submission(run)
        outsider = Client()
        self.assertEqual(outsider.get(reverse("engineering:run_detail", args=[run.id])).status_code, 404)
        self.assertEqual(self.post_submission(run, client=outsider).status_code, 404)
        for name in ["delivery", "reset"]:
            self.assertEqual(outsider.post(reverse("engineering:" + name, args=[run.id])).status_code, 404)
        self.assertEqual(Submission.objects.count(), 1)

    def test_same_demo_user_different_browsers_have_distinct_owners(self):
        user = User.objects.create_user("lab-demo")
        user.groups.add(Group.objects.create(name="Demo"))
        second = Client()
        self.client.force_login(user)
        second.force_login(user)
        first_run, second_run = self.start(), self.start(second)
        self.assertNotEqual(first_run.owner_hash, second_run.owner_hash)
        self.assertEqual(second.get(reverse("engineering:run_detail", args=[first_run.id])).status_code, 404)

    def test_owner_secret_not_persisted_and_login_deadline_is_not_extended(self):
        user = User.objects.create_user("lab-session")
        self.client.force_login(user)
        session = self.client.session
        deadline = timezone.now() + timedelta(minutes=7)
        session.set_expiry(deadline)
        session.save()
        run = self.start()
        self.assertNotEqual(run.owner_hash, self.client.session[services.SESSION_OWNER_KEY])
        self.assertEqual(Session.objects.get(session_key=session.session_key).expire_date, deadline)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("engineering:run_detail", args=[run.id])).status_code, 404)

    def test_relative_login_expiry_uses_persisted_deadline(self):
        user = User.objects.create_user("lab-relative")
        self.client.force_login(user)
        session = self.client.session
        session.set_expiry(1800)
        session.save()
        deadline = timezone.now() + timedelta(minutes=9)
        Session.objects.filter(session_key=session.session_key).update(expire_date=deadline)
        self.start()
        self.assertEqual(Session.objects.get(session_key=session.session_key).expire_date, deadline)

    def test_revoked_auth_session_cannot_read_or_mutate_existing_run(self):
        user = User.objects.create_user("lab-revoked-session")
        requests = [("run_detail", False), ("run_detail", True), ("submit", False),
                    ("submit", True), ("delivery", False), ("reset", False)]
        for action, partial in requests:
            with self.subTest(action=action, partial=partial):
                browser = Client()
                browser.force_login(user)
                run = self.start(browser)
                submission = new_submission(run)
                # Mirrors password-hash invalidation, including daily demo reset.
                user.set_unusable_password()
                user.save(update_fields=["password"])
                url = reverse("engineering:" + action, args=[run.id])
                headers = {"HTTP_HX_REQUEST": "true"} if partial else {}
                data = {"text": "How does a delivery receipt work?", "idempotency_key": uuid.uuid4(),
                        "event_id": submission.event.id, "scenario": "success"}
                response = browser.get(url, **headers) if action == "run_detail" else browser.post(url, data, **headers)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(services.SESSION_OWNER_KEY, browser.session)
                self.assertTrue(LabRun.objects.filter(pk=run.id).exists())
                self.assertEqual(Submission.objects.filter(run=run).count(), 1)
                self.assertEqual(ConsumerReceipt.objects.filter(event__submission__run=run).count(), 0)
                submission.event.refresh_from_db()
                self.assertEqual(submission.event.attempt_count, 0)

    def test_anonymous_owner_survives_lazy_auth_resolution(self):
        run = self.start()
        secret = self.client.session[services.SESSION_OWNER_KEY]
        self.assertEqual(self.client.get(reverse("engineering:run_detail", args=[run.id])).status_code, 200)
        self.assertEqual(self.client.session[services.SESSION_OWNER_KEY], secret)
        self.assertEqual(self.post_submission(run).status_code, 303)

    def test_session_expiry_and_24_hour_run_expiry(self):
        run = self.start()
        self.assertLessEqual(run.expires_at - run.created_at, timedelta(hours=24))
        Session.objects.filter(session_key=self.client.session.session_key).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(reverse("engineering:run_detail", args=[run.id])).status_code, 404)
        fresh = self.start()
        LabRun.objects.filter(pk=fresh.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(reverse("engineering:run_detail", args=[fresh.id])).status_code, 404)

    def test_three_run_cap_and_reset_only_owned_run(self):
        first, second = self.start(), self.start()
        self.start()
        self.assertEqual(self.client.post(reverse("engineering:create_run")).status_code, 429)
        foreign = new_run("f")
        self.assertEqual(self.client.post(reverse("engineering:reset", args=[first.id])).status_code, 303)
        self.assertFalse(LabRun.objects.filter(pk=first.id).exists())
        self.assertTrue(LabRun.objects.filter(pk=second.id).exists())
        self.assertTrue(LabRun.objects.filter(pk=foreign.id).exists())

    def test_method_enforcement_csrf_and_cache_headers(self):
        run = self.start()
        for name in ["submit", "delivery", "reset"]:
            self.assertEqual(self.client.get(reverse("engineering:" + name, args=[run.id])).status_code, 405)
        self.assertEqual(self.client.get(reverse("engineering:create_run")).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(reverse("engineering:create_run")).status_code, 403)
        for headers in [{}, {"HTTP_HX_REQUEST": "true"}]:
            response = self.client.get(reverse("engineering:run_detail", args=[run.id]), **headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertIn("noindex", response["X-Robots-Tag"])
            self.assertIn("HX-Request", response["Vary"])
            self.assertEqual(response["X-Lab-State"], "1")

    def test_htmx_validation_conflict_and_untrusted_text_are_safe(self):
        run = self.start()
        url = reverse("engineering:submit", args=[run.id])
        key = uuid.uuid4()
        response = self.client.post(url, {"text": "<script>alert(1)</script>", "idempotency_key": key}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 201)
        self.assertNotContains(response, "<script>alert(1)</script>", status_code=201)
        self.assertContains(response, "&lt;script&gt;", status_code=201)
        self.assertEqual(self.client.post(url, {"text": "changed text", "idempotency_key": key}, HTTP_HX_REQUEST="true").status_code, 409)
        self.assertEqual(self.client.post(url, {"text": "x"}, HTTP_HX_REQUEST="true").status_code, 400)

    def test_all_run_mutations_require_csrf_even_for_the_owner(self):
        run = self.start()
        self.post_submission(run)
        self.client.get(reverse("engineering:run_detail", args=[run.id]))
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        payloads = {
            "submit": {"text": "Another valid message", "idempotency_key": uuid.uuid4()},
            "delivery": {"event_id": OutboxEvent.objects.get().id, "scenario": "success"},
            "reset": {},
        }
        for name, payload in payloads.items():
            self.assertEqual(strict.post(reverse("engineering:" + name, args=[run.id]), payload).status_code, 403)
        self.assertTrue(LabRun.objects.filter(pk=run.pk).exists())
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(ConsumerReceipt.objects.count(), 0)

    def test_wrong_run_event_does_not_deliver(self):
        first, second = self.start(), self.start()
        self.post_submission(second)
        response = self.client.post(reverse("engineering:delivery", args=[first.id]), {"event_id": OutboxEvent.objects.get().id, "scenario": "success"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ConsumerReceipt.objects.count(), 0)

    def test_unavailable_model_does_not_block_submission(self):
        run = self.start()
        with patch("engineering.views.triage.classify", return_value={"status": "unavailable"}):
            self.assertEqual(self.post_submission(run).status_code, 303)
        self.assertEqual(Submission.objects.get().triage["status"], "unavailable")

    def test_normalization_expansion_returns_validation_error_not_server_error(self):
        run = self.start()
        response = self.post_submission(run, text="\u0344" * 751)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "after Unicode normalization", status_code=400)
        self.assertEqual(Submission.objects.count(), 0)

    @override_settings(ENGINEERING_LAB_ENABLED=False)
    def test_disabled_flag_returns_404_without_creating_records(self):
        self.assertEqual(self.client.get(reverse("engineering:index")).status_code, 404)
        self.assertEqual(self.client.post(reverse("engineering:create_run")).status_code, 404)
        self.assertEqual(self.client.get(reverse("engineering:permissions")).status_code, 404)
        self.assertEqual(LabRun.objects.count(), 0)

    def test_rate_limiter_is_ip_based_even_with_shared_login(self):
        self.client.force_login(User.objects.create_user("shared-rate-limit"))
        run = self.start()
        request = RequestFactory().post("/", REMOTE_ADDR="203.0.113.7")
        expected = _client_ip_identity(request, "engineering-submit", 300)
        with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=41) as increment:
            response = self.client.post(reverse("engineering:submit", args=[run.id]), REMOTE_ADDR="203.0.113.7")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertEqual(increment.call_args.args[0], expected)

    def test_throttled_submission_preserves_form_and_renders_recoverable_state(self):
        run = self.start()
        key = uuid.uuid4()
        data = {"text": "Preserve this unsent question about caching.", "idempotency_key": key}
        for headers in [{}, {"HTTP_HX_REQUEST": "true"}]:
            with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=41), patch("engineering.views.triage.classify") as classify:
                response = self.client.post(reverse("engineering:submit", args=[run.id]), data, **headers)
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response["X-Lab-State"], "1")
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertTrue(1 <= int(response["Retry-After"]) <= 300)
            self.assertContains(response, "then try again", status_code=429)
            self.assertContains(response, data["text"], status_code=429)
            self.assertContains(response, str(key), status_code=429)
            self.assertTemplateUsed(response, "engineering/_state.html" if headers else "engineering/run.html")
            classify.assert_not_called()
        self.assertEqual(Submission.objects.count(), 0)

    def test_throttled_delivery_and_reset_leave_run_unchanged(self):
        run = self.start()
        self.post_submission(run)
        event = OutboxEvent.objects.get()
        payloads = {"delivery": {"event_id": event.id, "scenario": "success"}, "reset": {}}
        for name, data in payloads.items():
            with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=100):
                response = self.client.post(reverse("engineering:" + name, args=[run.id]), data, HTTP_HX_REQUEST="true")
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response["X-Lab-State"], "1")
            self.assertContains(response, "Your saved lab records have not been changed", status_code=429)
            if name == "delivery":
                self.assertEqual(response.context["delivery_form"]["scenario"].value(), "success")
        self.assertEqual(OutboxEvent.objects.get().attempt_count, 0)
        self.assertTrue(LabRun.objects.filter(pk=run.id).exists())
        self.assertEqual(ConsumerReceipt.objects.count(), 0)

    def test_start_throttle_renders_guidance_without_creating_a_run(self):
        with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=13):
            response = self.client.post(reverse("engineering:create_run"))
        self.assertEqual(response.status_code, 429)
        self.assertTemplateUsed(response, "engineering/error.html")
        self.assertContains(response, "Slow down for a moment", status_code=429)
        self.assertTrue(response.context["is_throttled"])
        self.assertIn(response["Retry-After"], response.context["message"])
        self.assertEqual(LabRun.objects.count(), 0)

    def test_throttling_cannot_disclose_a_foreign_run(self):
        foreign = new_run()
        new_submission(foreign, text="Text that another session must not see.")
        with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=41):
            response = self.client.post(reverse("engineering:submit", args=[foreign.id]))
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Text that another session", status_code=404)

    def test_throttle_recovery_still_fails_closed_when_state_cannot_load(self):
        run = self.start()
        with patch("Domes.ratelimits._increment_rate_limit_bucket", return_value=41), patch("engineering.views.services.owned_run", side_effect=DatabaseError("injected failure")):
            response = self.client.post(reverse("engineering:submit", args=[run.id]))
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertNotContains(response, "injected failure", status_code=429)
        self.assertContains(response, "then try again", status_code=429)


@skipUnless(connection.vendor == "mysql", "Requires real MySQL locking/uniqueness semantics (CI MySQL 8).")
class LabMySQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.run = new_run()

    def concurrent(self, callbacks):
        barrier = Barrier(len(callbacks))
        def call(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callback()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
            futures = [pool.submit(call, callback) for callback in callbacks]
            return [future.result(timeout=30) for future in futures]

    def test_first_use_session_initialization_is_serialized(self):
        session_key, requests = preloaded_session_requests(4)
        def start(request):
            try:
                return services.create_run(request).id
            except services.LabCapacity:
                return None
            finally:
                request.session.save()
        results = self.concurrent([lambda request=request: start(request) for request in requests])
        run_ids = [run_id for run_id in results if run_id is not None]
        self.assertEqual(len(run_ids), 3)
        final_request = requests[0]
        final_request.session = SessionStore(session_key=session_key)
        self.assertEqual(len(set(LabRun.objects.filter(pk__in=run_ids).values_list("owner_hash", flat=True))), 1)
        for run_id in run_ids:
            self.assertEqual(services.owned_run(final_request, run_id).id, run_id)

    def test_duplicate_submissions_create_one_source_operation(self):
        key = uuid.uuid4()
        def operation():
            submission, created = services.submit(self.run, key, "The export button is broken.", PREDICTION)
            return submission.id, created
        results = self.concurrent([operation, operation])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(item[1] for item in results), [False, True])
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_conflicting_simultaneous_replays_have_one_winner(self):
        key = uuid.uuid4()
        def operation(text):
            try:
                services.submit(self.run, key, text, PREDICTION)
                return "created"
            except services.LabConflict:
                return "conflict"
        self.assertEqual(sorted(self.concurrent([lambda: operation("The export is broken."), lambda: operation("Please add exports.")])), ["conflict", "created"])
        self.assertEqual(Submission.objects.count(), 1)

    def test_source_rollback_remains_atomic_on_mysql(self):
        with patch("engineering.services.OutboxEvent.objects.create", side_effect=IntegrityError("injected")):
            with self.assertRaises(IntegrityError):
                new_submission(self.run)
        self.assertEqual(Submission.objects.count(), 0)

    def test_simultaneous_deliveries_share_one_effect(self):
        submission = new_submission(self.run)
        def deliver():
            try:
                return services.attempt_delivery(self.run, submission.event.id, "success")
            except services.AttemptBusy:
                return "busy"
        results = self.concurrent([deliver, deliver])
        self.assertIn("acknowledged", results)
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.get().attempt_count, 1)

    def test_lost_ack_committed_destination_survives_source_failure(self):
        submission = new_submission(self.run)
        with patch("engineering.services.finish_attempt", side_effect=RuntimeError("injected process interruption")):
            with self.assertRaises(RuntimeError):
                services.attempt_delivery(self.run, submission.event.id, "lost_ack")
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        OutboxEvent.objects.filter(pk=submission.event.id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        services.attempt_delivery(self.run, submission.event.id, "success")
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.get().status, "delivered")

    def test_expired_attempt_completes_after_successful_replacement(self):
        submission = new_submission(self.run)
        paused, resume = Event(), Event()
        finish = services.finish_attempt
        def delayed_finish(claim, outcome):
            if claim.attempt == 1:
                paused.set()
                if not resume.wait(timeout=15):
                    raise AssertionError("Replacement did not finish")
            return finish(claim, outcome)
        def first_attempt():
            close_old_connections()
            try:
                return services.attempt_delivery(self.run, submission.event.id, "lost_ack")
            finally:
                close_old_connections()
        with patch("engineering.services.finish_attempt", side_effect=delayed_finish), ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(first_attempt)
            try:
                self.assertTrue(paused.wait(timeout=10))
                OutboxEvent.objects.filter(pk=submission.event.id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
                self.assertEqual(services.attempt_delivery(self.run, submission.event.id, "success"), "acknowledged")
            finally:
                resume.set()
            self.assertEqual(first.result(timeout=15), "stale")
        self.assertEqual(ConsumerReceipt.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.get().status, "delivered")
