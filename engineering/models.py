"""Isolated lab records: deliberately no references to social-product objects."""

import uuid

from django.db import models
from django.db.models import Q


class LabRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_hash = models.CharField(max_length=64, db_index=True, editable=False)
    slot = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner_hash", "slot"], name="lab_owner_slot_unique"),
            models.CheckConstraint(condition=Q(slot__gte=0, slot__lte=2), name="lab_run_slot_bound"),
        ]


class Submission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(LabRun, on_delete=models.CASCADE, related_name="submissions")
    idempotency_key = models.UUIDField()
    text = models.CharField(max_length=1500)
    payload_hash = models.CharField(max_length=64, editable=False)
    triage = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["run", "idempotency_key"], name="lab_submission_key_unique")]


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ready for delivery"
        PROCESSING = "processing", "Attempt in progress"
        RETRY = "retry", "Ready to retry"
        DELIVERED = "delivered", "Acknowledged"
        EXHAUSTED = "exhausted", "Attempt limit reached"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name="event")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    claim_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    last_outcome = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, editable=False)

    @property
    def last_outcome_label(self):
        return {
            "acknowledged": "Delivery acknowledged",
            "fail_before_delivery": "Failure before delivery",
            "lost_ack": "Acknowledgement lost after delivery",
        }.get(self.last_outcome, "")

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(attempt_count__gte=0, attempt_count__lte=5), name="lab_attempt_limit"),
            models.CheckConstraint(
                condition=(Q(status="processing", claim_token__isnull=False, lease_expires_at__isnull=False)
                           | (~Q(status="processing") & Q(claim_token__isnull=True, lease_expires_at__isnull=True))),
                name="lab_claim_state_consistent",
            ),
        ]


class ConsumerReceipt(models.Model):
    """This row is both the deduplication receipt and the visible inbox effect."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(OutboxEvent, on_delete=models.CASCADE, related_name="receipt")
    text = models.CharField(max_length=1500)
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["delivered_at"]


class Trace(models.Model):
    id = models.BigAutoField(primary_key=True)
    run = models.ForeignKey(LabRun, on_delete=models.CASCADE, related_name="traces")
    event = models.ForeignKey(OutboxEvent, null=True, on_delete=models.CASCADE, related_name="traces")
    operation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    stage = models.CharField(max_length=40)
    detail = models.CharField(max_length=220)
    duration_ms = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.CheckConstraint(condition=Q(duration_ms__gte=0), name="lab_trace_nonnegative")]

    @property
    def stage_label(self):
        return {
            "source_committed": "Source recorded",
            "replay": "Original operation returned",
            "replay_conflict": "Conflicting replay rejected",
            "attempt_claimed": "Attempt claimed",
            "receipt_committed": "Destination recorded",
            "duplicate_prevented": "Duplicate effect prevented",
            "acknowledged": "Source acknowledged",
            "already_acknowledged": "Already acknowledged",
            "fail_before_delivery": "Failure before delivery",
            "lost_ack": "Acknowledgement lost",
            "stale_attempt": "Stale attempt ignored",
        }.get(self.stage, "Execution stage")
