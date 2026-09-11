"""Delete rate-limit buckets only after their expiration grace period."""

from time import time

from django.core.management.base import BaseCommand, CommandError

from Domes.models import RateLimitBucket


DEFAULT_GRACE_SECONDS = 24 * 60 * 60
MIN_GRACE_SECONDS = 60 * 60
DEFAULT_BATCH_SIZE = 1_000
MAX_BATCH_SIZE = 10_000
DEFAULT_MAX_BATCHES = 100
MAX_BATCHES = 10_000


class Command(BaseCommand):
    help = (
        "Delete expired rate-limit buckets in bounded batches after a "
        "conservative grace period."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--grace-seconds",
            type=int,
            default=DEFAULT_GRACE_SECONDS,
            help=(
                "Retain buckets for this many seconds after expiration "
                f"(default: {DEFAULT_GRACE_SECONDS}; minimum: {MIN_GRACE_SECONDS})."
            ),
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=(
                "Rows deleted per transaction "
                f"(default: {DEFAULT_BATCH_SIZE}; maximum: {MAX_BATCH_SIZE})."
            ),
        )
        parser.add_argument(
            "--max-batches",
            type=int,
            default=DEFAULT_MAX_BATCHES,
            help=(
                "Maximum batches per run "
                f"(default: {DEFAULT_MAX_BATCHES}; maximum: {MAX_BATCHES})."
            ),
        )

    def handle(self, *args, **options):
        grace_seconds = options["grace_seconds"]
        batch_size = options["batch_size"]
        max_batches = options["max_batches"]
        self._validate_options(grace_seconds, batch_size, max_batches)

        cutoff = int(time()) - grace_seconds
        deleted_total = 0

        for _ in range(max_batches):
            bucket_ids = list(
                RateLimitBucket.objects.filter(expires_at__lt=cutoff)
                .order_by("expires_at", "pk")
                .values_list("pk", flat=True)[:batch_size]
            )
            if not bucket_ids:
                break

            deleted, _ = RateLimitBucket.objects.filter(
                pk__in=bucket_ids,
                expires_at__lt=cutoff,
            ).delete()
            deleted_total += deleted

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_total} expired rate-limit bucket(s)."
            )
        )

        if RateLimitBucket.objects.filter(expires_at__lt=cutoff).exists():
            raise CommandError(
                "Cleanup reached --max-batches while expired buckets remain; "
                "run the command again or raise the bounded batch cap."
            )

    @staticmethod
    def _validate_options(grace_seconds, batch_size, max_batches):
        if grace_seconds < MIN_GRACE_SECONDS:
            raise CommandError(
                f"--grace-seconds must be at least {MIN_GRACE_SECONDS}."
            )
        if not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise CommandError(
                f"--batch-size must be between 1 and {MAX_BATCH_SIZE}."
            )
        if not 1 <= max_batches <= MAX_BATCHES:
            raise CommandError(
                f"--max-batches must be between 1 and {MAX_BATCHES}."
            )
