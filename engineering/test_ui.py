"""Rendered-form contracts, not a substitute for real-browser accessibility QA."""
from html.parser import HTMLParser
import uuid

from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse

from .models import ConsumerReceipt, LabRun, OutboxEvent, Submission


class Markup(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids = []
        self.forms = []
        self.current_form = None
        self.feed(content.decode())

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if tag == "form":
            self.current_form = {"attrs": values, "fields": []}
            self.forms.append(self.current_form)
        if tag in {"input", "textarea", "select"} and self.current_form is not None:
            self.current_form["fields"].append(values)

    def handle_endtag(self, tag):
        if tag == "form":
            self.current_form = None


@override_settings(ENGINEERING_LAB_ENABLED=True)
class LabRenderedWalkthroughTests(TransactionTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.index_url = reverse("engineering:index")
        self.client.get(self.index_url)

    def post(self, url, data=None, **extra):
        data = {**(data or {}), "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value}
        return self.client.post(url, data, **extra)

    def start(self):
        response = self.post(reverse("engineering:create_run"))
        self.assertEqual(response.status_code, 303)
        return LabRun.objects.get(), response["Location"]

    def test_plain_html_lost_ack_recovery_and_replay(self):
        run, location = self.start()
        empty = self.client.get(location)
        self.assertContains(empty, "The inbox is empty.")
        self.assertContains(empty, "Your delivery workbench")
        self.assertNotIn(b"\x00", empty.content)
        key = str(uuid.uuid4())
        text = "The export button returns an error after I select a date range."
        submit_url = reverse("engineering:submit", args=[run.id])
        response = self.post(submit_url, {"text": text, "idempotency_key": key})
        self.assertEqual(response.status_code, 303)
        submission = Submission.objects.get()
        self.assertContains(self.client.get(response["Location"]), "ML triage")
        delivery_url = reverse("engineering:delivery", args=[run.id])
        response = self.post(delivery_url, {"event_id": submission.event.id, "scenario": "lost_ack"})
        self.assertEqual(response.status_code, 303)
        lost = self.client.get(response["Location"])
        self.assertContains(lost, "Message received")
        self.assertContains(lost, "Acknowledgement lost")
        receipt_id = ConsumerReceipt.objects.get().id
        response = self.post(delivery_url, {"event_id": submission.event.id, "scenario": "success"})
        self.assertEqual(response.status_code, 303)
        recovered = self.client.get(response["Location"])
        self.assertContains(recovered, "Duplicate effect prevented")
        self.assertContains(recovered, "Source acknowledged")
        self.assertEqual(ConsumerReceipt.objects.get().id, receipt_id)
        replay = self.post(submit_url, {"text": text, "idempotency_key": key})
        self.assertEqual(replay.status_code, 303)
        self.assertContains(self.client.get(replay["Location"]), "No extra event was created")
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)
        self.assertEqual(ConsumerReceipt.objects.count(), 1)

    def test_multiple_operations_have_unique_ids_and_csrf_forms(self):
        run, location = self.start()
        for text in ["Could we add an export preview?", "Why does this deployment use a proxy?"]:
            self.post(reverse("engineering:submit", args=[run.id]), {"text": text, "idempotency_key": uuid.uuid4()})
        response = self.client.get(location)
        self.assertContains(response, "Saved operation 1")
        self.assertContains(response, "Saved operation 2")
        markup = Markup(response.content)
        self.assertEqual(len(markup.ids), len(set(markup.ids)))
        self.assertGreaterEqual(len(markup.forms), 6)
        for form in markup.forms:
            self.assertEqual(form["attrs"].get("method"), "post")
            self.assertTrue(any(field.get("name") == "csrfmiddlewaretoken" for field in form["fields"]))
        self.assertContains(response, 'maxlength="1500"')
        self.assertContains(response, 'href="#lab-main"')

    def test_partial_validation_and_full_fallback_are_complete(self):
        run, location = self.start()
        url = reverse("engineering:submit", args=[run.id])
        key = uuid.uuid4()
        self.post(url, {"text": "The page fails to load after login.", "idempotency_key": key})
        conflict = self.post(url, {"text": "A different request.", "idempotency_key": key}, HTTP_HX_REQUEST="true")
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict["X-Lab-State"], "1")
        self.assertContains(conflict, 'id="lab-state"', status_code=409)
        self.assertContains(conflict, "Restore the original text or use a new key", status_code=409)
        self.assertNotContains(conflict, "<!doctype html>", status_code=409)
        invalid = self.post(url, {"text": "x", "idempotency_key": "bad-key"})
        self.assertContains(invalid, "<!doctype html>", status_code=400)
        self.assertContains(invalid, 'aria-invalid="true"', status_code=400)
        self.assertIn("no-store", invalid["Cache-Control"])
        self.assertIn("noindex", invalid["X-Robots-Tag"])

    def test_invalid_key_is_visible_and_associated_in_full_and_partial_responses(self):
        run, _ = self.start()
        url = reverse("engineering:submit", args=[run.id])
        for extra in ({}, {"HTTP_HX_REQUEST": "true"}):
            invalid = self.post(url, {
                "text": "How do I inspect the delivery receipt?",
                "idempotency_key": "not-a-uuid",
            }, **extra)
            self.assertEqual(invalid.status_code, 400)
            self.assertContains(invalid, '<details class="lab-key-details" open>', status_code=400)
            self.assertContains(invalid, 'aria-describedby="key-hint key-errors" aria-invalid="true"', status_code=400)
            self.assertContains(invalid, 'id="key-errors"', status_code=400)
            self.assertEqual(Submission.objects.count(), 0)

    def test_model_unavailable_copy_and_hypothetical_permissions(self):
        from unittest.mock import patch
        with patch("engineering.triage.model_card", return_value={"status": "unavailable"}):
            response = self.client.get(self.index_url)
        self.assertContains(response, "ML triage is currently unavailable")
        self.assertContains(response, "Start a private lab run")
        self.assertNotIn(b"\x00", response.content)
        permissions = self.client.get(reverse("engineering:permissions"), {"role": "outsider", "resource": "private"})
        self.assertContains(permissions, "Who can do what?")
        self.assertContains(permissions, "Denied")
        self.assertContains(permissions, 'method="get"')
