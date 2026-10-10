from datetime import timedelta
from io import StringIO
import os
from pathlib import Path
import runpy
from unittest.mock import patch
import uuid

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from Domes.models import Dome, RateLimitBucket
from .models import LabRun, MaintenanceLease


@override_settings(DEMO_ACCOUNT_ENABLED=True, DEMO_USERNAME="maintenance-test-guest")
class MaintenanceTests(TestCase):
    def run_maintenance(self):
        output = StringIO()
        call_command("maintain_demo_sandbox", stdout=output)
        return output.getvalue()

    def test_daily_reset_is_idempotent_and_preserves_unrelated_accounts(self):
        owner = User.objects.create_user("unrelated-owner")
        first = self.run_maintenance()
        guest = User.objects.get(username="maintenance-test-guest")
        dome_id = Dome.objects.get(user=guest).pk
        self.assertFalse(guest.has_usable_password())
        self.assertIn("Cleaned at most", first)
        self.assertIn("already reset today", self.run_maintenance())
        self.assertEqual(Dome.objects.get(user=guest).pk, dome_id)
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        lease = MaintenanceLease.objects.get()
        self.assertIsNone(lease.token)
        self.assertIsNone(lease.expires_at)
        self.assertEqual(lease.last_reset_at.date(), timezone.now().date())

    def test_active_lease_prevents_reset_and_expired_lease_recovers(self):
        lease = MaintenanceLease.objects.create(name="demo-maintenance", token=uuid.uuid4(), expires_at=timezone.now() + timedelta(minutes=5))
        self.assertIn("already leased", self.run_maintenance())
        self.assertFalse(User.objects.filter(username="maintenance-test-guest").exists())
        lease.expires_at = timezone.now() - timedelta(seconds=1)
        lease.save()
        self.run_maintenance()
        self.assertTrue(User.objects.filter(username="maintenance-test-guest").exists())

    def test_expired_cleanup_is_bounded_and_leaves_live_records(self):
        now = timezone.now()
        MaintenanceLease.objects.create(name="demo-maintenance", last_reset_at=now)
        LabRun.objects.bulk_create([LabRun(owner_hash=str(i).zfill(64), slot=0, expires_at=now - timedelta(days=1)) for i in range(502)])
        live = LabRun.objects.create(owner_hash="live".ljust(64, "x"), slot=0, expires_at=now + timedelta(days=1))
        Session.objects.bulk_create([Session(session_key=str(i).zfill(32), session_data="", expire_date=now - timedelta(days=1)) for i in range(1002)])
        self.run_maintenance()
        self.assertEqual(LabRun.objects.filter(expires_at__lte=now).count(), 2)
        self.assertTrue(LabRun.objects.filter(pk=live.pk).exists())
        self.assertEqual(Session.objects.count(), 2)

    @override_settings(DEMO_ACCOUNT_ENABLED=False)
    def test_disabled_demo_refuses_mutation(self):
        with self.assertRaises(CommandError):
            self.run_maintenance()
        self.assertFalse(MaintenanceLease.objects.exists())

    def test_seed_failure_keeps_lease_for_bounded_retry_and_preserves_real_user(self):
        real = User.objects.create_user("maintenance-test-guest")
        with self.assertRaises(CommandError):
            self.run_maintenance()
        self.assertTrue(User.objects.filter(pk=real.pk).exists())
        lease = MaintenanceLease.objects.get()
        self.assertIsNotNone(lease.token)
        self.assertIsNone(lease.last_reset_at)


class WasmerProfileTests(SimpleTestCase):
    variables = {"DJANGO_SECRET_KEY": "test-profile-key-" + "x" * 60,
                 "DJANGO_ALLOWED_HOSTS": "example.wasmer.app",
                 "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.wasmer.app",
                 "PUBLIC_SITE_URL": "https://example.wasmer.app",
                 "DB_HOST": "managed-db.internal", "DB_PORT": "3306", "DB_NAME": "demo",
                 "DB_USERNAME": "injected-user", "DB_USER": "ignored-legacy-user", "DB_PASSWORD": "test-only"}

    def profile(self, **changes):
        with patch.dict(os.environ, {**self.variables, **changes}, clear=True):
            return runpy.run_module("paradome.settings.wasmer")

    def test_injected_username_secure_cookies_and_disabled_services(self):
        profile = self.profile()
        self.assertEqual(profile["DATABASES"]["default"]["USER"], "injected-user")
        self.assertEqual(profile["DATABASES"]["default"]["OPTIONS"]["ssl_mode"], "REQUIRED")
        self.assertTrue(profile["SESSION_COOKIE_SECURE"])
        self.assertTrue(profile["SESSION_PAGES_NOSTORE"])
        self.assertFalse(profile["CHAT_REALTIME_ENABLED"])
        self.assertFalse(profile["CONTACT_FORM_ENABLED"])
        self.assertEqual(profile["DEMO_USERNAME"], "paradome-wasmer-guest")

    def test_hosts_origins_and_private_storage_fail_closed(self):
        for changes in ({"DJANGO_SECRET_KEY": "short"}, {"DB_USERNAME": ""}, {"DJANGO_ALLOWED_HOSTS": "*"}, {"PUBLIC_SITE_URL": "http://example.wasmer.app"}, {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://foreign.wasmer.app"}, {"PRIVATE_MEDIA_ROOT": "/tmp/media"}, {"PRIVATE_MEDIA_ROOT": "/data/../tmp/media"}, {"PRIVATE_MEDIA_ROOT": "relative/media"}):
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.profile(**changes)
