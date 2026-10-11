from datetime import timedelta
import uuid

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from Domes.models import RateLimitBucket
from engineering.models import MaintenanceLease
from engineering.services import purge_expired_runs


class Command(BaseCommand):
    help = "Once-per-UTC-day sandbox reset and bounded expired-data cleanup, under a DB lease."

    def handle(self, *args, **options):
        if not settings.DEMO_ACCOUNT_ENABLED:
            raise CommandError("Enable the dedicated demo account before scheduled maintenance")
        token = uuid.uuid4()
        MaintenanceLease.objects.get_or_create(name="demo-maintenance")
        with transaction.atomic():
            lease = MaintenanceLease.objects.select_for_update().get(name="demo-maintenance")
            now = timezone.now()
            if lease.token and lease.expires_at > now:
                self.stdout.write("Maintenance is already leased; no reset performed.")
                return
            lease.token, lease.expires_at = token, now + timedelta(minutes=5)
            lease.save(update_fields=["token", "expires_at"])
        # Keep this root lock for the bounded reset. A replacement job cannot
        # steal the lease while writes are in progress, even if a deadline passes.
        with transaction.atomic():
            lease = MaintenanceLease.objects.select_for_update().get(name="demo-maintenance")
            if lease.token != token or lease.expires_at <= timezone.now():
                raise CommandError("Maintenance lease no longer belongs to this job")
            now = timezone.now()
            if lease.last_reset_at is None or lease.last_reset_at.date() < now.date():
                call_command("reset_demo_sandbox", stdout=self.stdout)
                lease.last_reset_at = now
            else:
                self.stdout.write("Sandbox already reset today; only expired data will be cleaned.")
                purge_expired_runs(batch_size=100, max_batches=5)
            session_ids = list(Session.objects.filter(expire_date__lte=now).order_by("expire_date").values_list("pk", flat=True)[:1000])
            Session.objects.filter(pk__in=session_ids, expire_date__lte=now).delete()
            bucket_ids = list(RateLimitBucket.objects.filter(expires_at__lte=int(now.timestamp())).order_by("expires_at").values_list("pk", flat=True)[:1000])
            RateLimitBucket.objects.filter(pk__in=bucket_ids, expires_at__lte=int(now.timestamp())).delete()
            lease.token = lease.expires_at = None
            lease.save(update_fields=["token", "expires_at", "last_reset_at"])
        self.stdout.write(f"Cleaned at most 500 expired runs, {len(session_ids)} expired sessions, and {len(bucket_ids)} expired rate-limit buckets.")
