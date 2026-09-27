"""Request-driven outbox exercise; never calls a real transport or product model."""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import secrets
from time import perf_counter
import uuid

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from .forms import SCENARIOS, normalize_submission
from .models import ConsumerReceipt, LabRun, OutboxEvent, Submission, Trace

SESSION_OWNER_KEY = "engineering_owner_secret"
MAX_SUBMISSIONS = 10
MAX_TRACES = 80
MAX_ATTEMPTS = 5
LEASE_SECONDS = 15


class LabConflict(Exception):
    pass


class LabCapacity(Exception):
    pass


class AttemptBusy(LabConflict):
    pass


@dataclass(frozen=True)
class Claim:
    run_id: uuid.UUID
    event_id: uuid.UUID
    token: uuid.UUID
    operation_id: uuid.UUID
    scenario: str
    attempt: int


def owner_hash(request, *, create=False):
    # AuthenticationMiddleware is lazy: resolve it before trusting session data
    # so a changed password hash can flush the old owner secret first. Anonymous
    # sessions remain valid owners; this is not a login requirement.
    authenticated = request.user.is_authenticated
    secret = request.session.get(SESSION_OWNER_KEY)
    if not secret and create:
        # Independent requests may have loaded the same session before either
        # saved it. Initialize once in the canonical DB row, not in each stale
        # request cache, or the last session save can strand another tab's run.
        if request.session.session_key is None:
            request.session.create()
        with transaction.atomic():
            try:
                session = Session.objects.select_for_update().get(session_key=request.session.session_key)
            except Session.DoesNotExist as exc:
                raise Http404("This session has ended. Start a new run.") from exc
            if session.expire_date <= timezone.now():
                raise Http404("This session has ended. Start a new run.")
            data = session.get_decoded()
            secret = data.get(SESSION_OWNER_KEY)
            if not isinstance(secret, str) or not secret:
                secret = secrets.token_urlsafe(32)
                data[SESSION_OWNER_KEY] = secret
                session.session_data = request.session.encode(data)
                session.save(update_fields=["session_data"])
            expiry = session.expire_date
        # Converge cached copies before SessionMiddleware saves them. Preserve
        # the persisted auth deadline rather than restarting a relative expiry.
        request.session[SESSION_OWNER_KEY] = secret
        if authenticated and not request.session.get_expire_at_browser_close():
            request.session.set_expiry(expiry)
    if not isinstance(secret, str) or not secret:
        return None
    return hmac.new(
        str(settings.SECRET_KEY).encode(), b"engineering-owner-v1\0" + secret.encode(), hashlib.sha256,
    ).hexdigest()


def owned_run(request, run_id):
    fingerprint = owner_hash(request)
    if fingerprint is None:
        raise Http404("This lab run is unavailable. Start a new run.")
    try:
        return LabRun.objects.get(pk=run_id, owner_hash=fingerprint, expires_at__gt=timezone.now())
    except LabRun.DoesNotExist as exc:
        raise Http404("This lab run is unavailable. Start a new run.") from exc


def _lock_run(run_id):
    try:
        run = LabRun.objects.select_for_update().get(pk=run_id)
    except LabRun.DoesNotExist as exc:
        raise Http404("This lab run has expired. Start a new run.") from exc
    # Evaluate time after acquiring the lock: time spent waiting for another
    # request must not let an already-expired run accept another write.
    if run.expires_at <= timezone.now():
        raise Http404("This lab run has expired. Start a new run.")
    return run


def _trace(run, event, operation_id, stage, detail, started):
    # All callers hold the run row lock: history trimming and writes are bounded
    # even when two browser tabs execute requests together.
    Trace.objects.create(
        run=run, event=event, operation_id=operation_id, stage=stage,
        detail=detail, duration_ms=max(0, (perf_counter() - started) * 1000),
    )
    stale_ids = list(Trace.objects.filter(run=run).order_by("-id").values_list("id", flat=True)[MAX_TRACES:])
    if stale_ids:
        Trace.objects.filter(pk__in=stale_ids).delete()


def create_run(request):
    fingerprint = owner_hash(request, create=True)
    now = timezone.now()
    # The unique (owner, slot) constraint makes the per-browser cap race-safe.
    with transaction.atomic():
        # Lock roots before Django collects cascading children. An in-flight
        # writer that locked just before expiry must finish before collection.
        expired = list(LabRun.objects.select_for_update().filter(
            owner_hash=fingerprint, expires_at__lte=now,
        ).values_list("pk", flat=True))
        LabRun.objects.filter(pk__in=expired).delete()
    for slot in range(3):
        try:
            with transaction.atomic():
                return LabRun.objects.create(owner_hash=fingerprint, slot=slot, expires_at=now + timedelta(hours=24))
        except IntegrityError:
            continue
    raise LabCapacity("This browser already has three runs. Reset one of them to start again.")


def reset_run(request, run):
    with transaction.atomic():
        locked = _lock_run(run.id)
        if locked.owner_hash != owner_hash(request):
            raise Http404
        locked.delete()
        return create_run(request)


def submit(run, key, text, triage):
    started = perf_counter()
    text = normalize_submission(text)
    if not 3 <= len(text) <= 1500:
        raise ValueError("Submission text is outside the permitted size.")
    digest = hashlib.sha256(text.encode()).hexdigest()
    operation = uuid.uuid4()
    with transaction.atomic():
        locked = _lock_run(run.id)
        existing = Submission.objects.filter(run=locked, idempotency_key=key).select_related("event").first()
        if existing is not None:
            if existing.payload_hash != digest or existing.text != text:
                _trace(locked, existing.event, operation, "replay_conflict", "The key already belongs to different text. No operation was changed.", started)
                # Raise outside the transaction so the explanatory trace survives.
                conflict = True
            else:
                _trace(locked, existing.event, operation, "replay", "Identical request: returned the original submission and event.", started)
                return existing, False
        else:
            conflict = False
            if locked.submissions.count() >= MAX_SUBMISSIONS:
                raise LabCapacity("This run has reached its ten-submission limit. Reset it to continue.")
            submission = Submission.objects.create(run=locked, idempotency_key=key, text=text, payload_hash=digest, triage=triage)
            event = OutboxEvent.objects.create(submission=submission)
            _trace(locked, event, operation, "source_committed", "Submission and pending event saved in one source transaction.", started)
    if conflict:
        raise LabConflict("This idempotency key was already used for different text. Restore the original text or use a new key.")
    return submission, True


def claim_delivery(run, event_id, scenario):
    if scenario not in dict(SCENARIOS):
        raise ValueError("Unknown delivery scenario.")
    started = perf_counter()
    with transaction.atomic():
        locked = _lock_run(run.id)
        try:
            event = OutboxEvent.objects.select_for_update().get(pk=event_id, submission__run=locked)
        except OutboxEvent.DoesNotExist as exc:
            raise Http404 from exc
        now = timezone.now()
        if event.status == OutboxEvent.Status.DELIVERED:
            _trace(locked, event, uuid.uuid4(), "already_acknowledged", "The event is already acknowledged. No new attempt or inbox effect.", started)
            return None
        if event.status == OutboxEvent.Status.PROCESSING and event.lease_expires_at > now:
            raise AttemptBusy("An attempt is in progress. Wait for its short lease to finish, then try again.")
        if event.attempt_count >= MAX_ATTEMPTS:
            event.status = OutboxEvent.Status.EXHAUSTED
            event.claim_token = None
            event.lease_expires_at = None
            event.save(update_fields=["status", "claim_token", "lease_expires_at"])
            exhausted = True
        else:
            exhausted = False
            claim = Claim(locked.id, event.id, uuid.uuid4(), uuid.uuid4(), scenario, event.attempt_count + 1)
            event.attempt_count = claim.attempt
            event.status = OutboxEvent.Status.PROCESSING
            event.claim_token = claim.token
            event.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            event.save(update_fields=["attempt_count", "status", "claim_token", "lease_expires_at"])
            _trace(locked, event, claim.operation_id, "attempt_claimed", f"Attempt {claim.attempt} claimed with a {LEASE_SECONDS}-second lease.", started)
    if exhausted:
        raise LabCapacity("All five attempts have been used. Reset the run to try another walkthrough.")
    return claim


def commit_receipt(claim):
    """Sink transaction commits before acknowledgement, including lost-ack mode."""
    started = perf_counter()
    with transaction.atomic():
        run = _lock_run(claim.run_id)
        event = OutboxEvent.objects.select_for_update().select_related("submission").get(pk=claim.event_id, submission__run=run)
        if event.claim_token != claim.token or event.status != OutboxEvent.Status.PROCESSING or event.lease_expires_at <= timezone.now():
            return "stale"
        receipt, created = ConsumerReceipt.objects.get_or_create(event=event, defaults={"text": event.submission.text})
        outcome = "receipt_committed" if created else "duplicate_prevented"
        detail = "One destination receipt and inbox effect committed together." if created else "The destination already has this event. Its unique receipt prevented another inbox effect."
        _trace(run, event, claim.operation_id, outcome, detail, started)
    return outcome


def finish_attempt(claim, outcome):
    """A stale token cannot acknowledge, overwrite, or release a replacement."""
    started = perf_counter()
    with transaction.atomic():
        run = _lock_run(claim.run_id)
        event = OutboxEvent.objects.select_for_update().get(pk=claim.event_id, submission__run=run)
        if event.claim_token != claim.token or event.status != OutboxEvent.Status.PROCESSING or event.lease_expires_at <= timezone.now():
            _trace(run, event, claim.operation_id, "stale_attempt", "A stale attempt was ignored; the current attempt's state was preserved.", started)
            return "stale"
        acknowledged = outcome == "acknowledged"
        if acknowledged and not ConsumerReceipt.objects.filter(event=event).exists():
            raise LabConflict("The destination has not recorded this event.")
        event.status = OutboxEvent.Status.DELIVERED if acknowledged else (OutboxEvent.Status.EXHAUSTED if event.attempt_count >= MAX_ATTEMPTS else OutboxEvent.Status.RETRY)
        event.last_outcome = outcome
        event.acknowledged_at = timezone.now() if acknowledged else None
        event.claim_token = None
        event.lease_expires_at = None
        event.save(update_fields=["status", "last_outcome", "acknowledged_at", "claim_token", "lease_expires_at"])
        detail = {
            "acknowledged": "Source acknowledgement committed. The destination contains exactly one effect.",
            "fail_before_delivery": "Simulated failure before the destination transaction. No inbox effect was written.",
            "lost_ack": "Destination committed, but its acknowledgement was deliberately lost. A retry is safe.",
        }[outcome]
        _trace(run, event, claim.operation_id, outcome, detail, started)
    return outcome


def attempt_delivery(run, event_id, scenario):
    # Do not wrap this coordinator in an outer atomic block: the sink transaction
    # must remain committed when the source loses its acknowledgement.
    if transaction.get_connection().in_atomic_block:
        # Django TestCase itself uses an atomic wrapper; tests call primitives
        # there, while TransactionTestCase verifies this public boundary.
        raise RuntimeError("Lab delivery must run outside an enclosing transaction.")
    claim = claim_delivery(run, event_id, scenario)
    if claim is None:
        return "already_acknowledged"
    if scenario == "fail_before_delivery":
        return finish_attempt(claim, "fail_before_delivery")
    receipt_outcome = commit_receipt(claim)
    if receipt_outcome == "stale":
        return "stale"
    return finish_attempt(claim, "lost_ack" if scenario == "lost_ack" else "acknowledged")


def purge_expired_runs(*, batch_size=100, max_batches=5):
    if not 1 <= batch_size <= 500 or not 1 <= max_batches <= 20:
        raise ValueError("Cleanup bounds must be 1–500 records and 1–20 batches.")
    total = 0
    cutoff = timezone.now()
    for _ in range(max_batches):
        ids = list(LabRun.objects.filter(expires_at__lte=cutoff).order_by("expires_at").values_list("pk", flat=True)[:batch_size])
        if not ids:
            break
        with transaction.atomic():
            # Lock roots before cascading, matching the service lock order.
            doomed = list(LabRun.objects.select_for_update().filter(pk__in=ids, expires_at__lte=cutoff).values_list("pk", flat=True))
            LabRun.objects.filter(pk__in=doomed).delete()
            total += len(doomed)
    return total
