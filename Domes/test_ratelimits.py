from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings

from .models import RateLimitBucket
from .ratelimits import _rate_limit_identities, _rate_limit_response


@override_settings(SECRET_KEY="rate-limit-test-secret")
class DatabaseRateLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, *, ip="203.0.113.10", username="", user=None):
        request = self.factory.post(
            "/limited/",
            {"username": username},
            REMOTE_ADDR=ip,
        )
        if user is not None:
            request.user = user
        return request

    def test_subjects_are_keyed_domain_separated_hmac_digests(self):
        first = self.request(username="  ExampleUser  ")
        second = self.request(username="exampleuser")
        first_ip, first_account = _rate_limit_identities(
            first,
            "login",
            300,
            ("ip", "account"),
        )
        second_ip, second_account = _rate_limit_identities(
            second,
            "login",
            300,
            ("ip", "account"),
        )

        self.assertRegex(first_ip, r"\A[0-9a-f]{64}\Z")
        self.assertNotIn("203.0.113.10", first_ip)
        self.assertNotIn("exampleuser", first_account)
        self.assertEqual(first_ip, second_ip)
        self.assertEqual(first_account, second_account)
        self.assertNotEqual(first_ip, first_account)

        registration_subject = _rate_limit_identities(
            first,
            "registration",
            300,
            ("ip",),
        )[0]
        self.assertNotEqual(first_ip, registration_subject)
        with self.settings(SECRET_KEY="different-rate-limit-secret"):
            rotated_key_subject = _rate_limit_identities(
                first,
                "login",
                300,
                ("ip",),
            )[0]
        self.assertNotEqual(first_ip, rotated_key_subject)

    def test_registration_stays_ip_only_while_login_tracks_account_separately(self):
        first = self.request(username="first-account")
        second = self.request(username="second-account")

        self.assertEqual(
            _rate_limit_identities(first, "registration", 3600, ("ip",)),
            _rate_limit_identities(second, "registration", 3600, ("ip",)),
        )
        first_login = _rate_limit_identities(
            first,
            "login",
            300,
            ("ip", "account"),
        )
        second_login = _rate_limit_identities(
            second,
            "login",
            300,
            ("ip", "account"),
        )
        self.assertEqual(first_login[0], second_login[0])
        self.assertNotEqual(first_login[1], second_login[1])

    def test_authenticated_requests_honor_explicit_identity_modes(self):
        attacker = get_user_model().objects.create_user(username="attacker")
        first = self.request(
            ip="203.0.113.30",
            username="TargetOne",
            user=attacker,
        )
        second = self.request(
            ip="203.0.113.31",
            username="TargetTwo",
            user=attacker,
        )

        first_ip, first_account = _rate_limit_identities(
            first,
            "login",
            300,
            ("account", "ip"),
        )
        second_ip, second_account = _rate_limit_identities(
            second,
            "login",
            300,
            ("ip", "account"),
        )

        self.assertNotEqual(first_ip, second_ip)
        self.assertNotEqual(first_account, second_account)

        default_identity = _rate_limit_identities(first, "content", 60)
        authenticated_only_identity = _rate_limit_identities(
            first,
            "content",
            60,
            ("ip", "account"),
            authenticated_only=True,
        )
        self.assertEqual(len(default_identity), 1)
        self.assertEqual(default_identity, authenticated_only_identity)

    @patch("Domes.ratelimits.time", return_value=125.75)
    def test_authenticated_login_enforces_ip_then_target_account(self, _now):
        attacker = get_user_model().objects.create_user(username="attacker")
        first = self.request(
            ip="203.0.113.40",
            username="TargetOne",
            user=attacker,
        )
        first_ip, first_account = _rate_limit_identities(
            first,
            "login",
            60,
            ("ip", "account"),
        )
        self.assertIsNone(
            _rate_limit_response(
                first,
                "login",
                1,
                60,
                identity_modes=("ip", "account"),
            )
        )

        rotated_target = self.request(
            ip="203.0.113.40",
            username="TargetTwo",
            user=attacker,
        )
        _, rotated_account = _rate_limit_identities(
            rotated_target,
            "login",
            60,
            ("ip", "account"),
        )
        self.assertEqual(
            _rate_limit_response(
                rotated_target,
                "login",
                1,
                60,
                identity_modes=("ip", "account"),
            ).status_code,
            429,
        )
        self.assertFalse(
            RateLimitBucket.objects.filter(
                subject_hash=rotated_account,
                window_start=120,
            ).exists()
        )

        rotated_ip = self.request(
            ip="203.0.113.41",
            username=" targetone ",
            user=attacker,
        )
        second_ip, normalized_account = _rate_limit_identities(
            rotated_ip,
            "login",
            60,
            ("ip", "account"),
        )
        self.assertEqual(normalized_account, first_account)
        self.assertEqual(
            _rate_limit_response(
                rotated_ip,
                "login",
                1,
                60,
                identity_modes=("ip", "account"),
            ).status_code,
            429,
        )

        counts = dict(
            RateLimitBucket.objects.values_list("subject_hash", "count")
        )
        self.assertEqual(
            counts,
            {
                first_ip: 2,
                first_account: 2,
                second_ip: 1,
            },
        )
        self.assertFalse(
            RateLimitBucket.objects.exclude(expires_at=180).exists()
        )

    @patch("Domes.ratelimits.time", return_value=125.75)
    def test_ip_denial_bounds_rows_for_rotating_usernames(self, _now):
        initial_requests = [
            self.request(username=f"rotated-{attempt}") for attempt in range(2)
        ]
        for request in initial_requests:
            self.assertIsNone(
                _rate_limit_response(
                    request,
                    "login",
                    2,
                    60,
                    identity_modes=("ip", "account"),
                )
            )

        for attempt in range(2, 52):
            response = _rate_limit_response(
                self.request(username=f"rotated-{attempt}"),
                "login",
                2,
                60,
                identity_modes=("ip", "account"),
            )
            self.assertEqual(response.status_code, 429)

        ip_subject = _rate_limit_identities(
            initial_requests[0],
            "login",
            60,
            ("ip",),
        )[0]
        self.assertEqual(RateLimitBucket.objects.count(), 3)
        self.assertEqual(
            RateLimitBucket.objects.get(subject_hash=ip_subject).count,
            52,
        )

    @patch("Domes.ratelimits.time", return_value=125.75)
    def test_fixed_window_counter_and_retry_after_share_one_time_capture(self, now):
        request = self.request()

        for _ in range(2):
            self.assertIsNone(
                _rate_limit_response(request, "fixed-window", 2, 60)
            )
        response = _rate_limit_response(request, "fixed-window", 2, 60)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "55")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(now.call_count, 3)
        bucket = RateLimitBucket.objects.get()
        self.assertEqual(bucket.window_start, 120)
        self.assertEqual(bucket.expires_at, 180)
        self.assertEqual(bucket.count, 3)

    @patch(
        "Domes.ratelimits.time",
        side_effect=(125.75, 181.25, 126.5),
    )
    def test_interleaved_windows_never_delete_or_reset_old_count(self, now):
        request = self.request()
        subject_hash = _rate_limit_identities(
            request,
            "interleaved",
            60,
            ("ip",),
        )[0]

        self.assertIsNone(_rate_limit_response(request, "interleaved", 5, 60))
        self.assertIsNone(_rate_limit_response(request, "interleaved", 5, 60))
        self.assertIsNone(_rate_limit_response(request, "interleaved", 5, 60))

        self.assertEqual(
            list(
                RateLimitBucket.objects.filter(subject_hash=subject_hash)
                .order_by("window_start")
                .values_list("window_start", "expires_at", "count")
            ),
            [(120, 180, 2), (180, 240, 1)],
        )
        self.assertEqual(now.call_count, 3)

    @patch("Domes.ratelimits.time", return_value=125.75)
    @patch(
        "Domes.ratelimits._increment_rate_limit_bucket",
        side_effect=DatabaseError("counter unavailable"),
    )
    def test_counter_database_failure_fails_closed(self, _increment, now):
        with self.assertLogs("Domes.ratelimits", level="ERROR"):
            response = _rate_limit_response(
                self.request(),
                "database-failure",
                5,
                60,
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "55")
        self.assertEqual(now.call_count, 1)


class RateLimitCleanupCommandTests(TestCase):
    def create_bucket(self, sequence, expires_at):
        return RateLimitBucket.objects.create(
            subject_hash=f"{sequence:064x}",
            window_start=max(0, expires_at - 60),
            expires_at=expires_at,
            count=1,
        )

    @patch(
        "Domes.management.commands.cleanup_rate_limit_buckets.time",
        return_value=200_000,
    )
    def test_cleanup_uses_conservative_default_and_strict_cutoff(self, _now):
        expired = self.create_bucket(1, 113_599)
        boundary = self.create_bucket(2, 113_600)
        fresh = self.create_bucket(3, 113_601)
        stdout = StringIO()

        call_command("cleanup_rate_limit_buckets", stdout=stdout)

        self.assertFalse(
            RateLimitBucket.objects.filter(pk=expired.pk).exists()
        )
        self.assertEqual(
            RateLimitBucket.objects.filter(
                pk__in=(boundary.pk, fresh.pk)
            ).count(),
            2,
        )
        self.assertIn("Deleted 1 expired rate-limit bucket(s).", stdout.getvalue())

    @patch(
        "Domes.management.commands.cleanup_rate_limit_buckets.time",
        return_value=200_000,
    )
    def test_cleanup_is_batched_and_fails_if_the_cap_leaves_rows(self, _now):
        for sequence in range(1, 6):
            self.create_bucket(sequence, 100_000 + sequence)

        with self.assertRaisesMessage(CommandError, "reached --max-batches"):
            call_command(
                "cleanup_rate_limit_buckets",
                grace_seconds=3_600,
                batch_size=2,
                max_batches=2,
                stdout=StringIO(),
                stderr=StringIO(),
            )

        self.assertEqual(RateLimitBucket.objects.count(), 1)

    def test_cleanup_rejects_unsafe_bounds(self):
        cases = (
            ({"grace_seconds": 3_599}, "--grace-seconds"),
            ({"batch_size": 0}, "--batch-size"),
            ({"batch_size": 10_001}, "--batch-size"),
            ({"max_batches": 0}, "--max-batches"),
            ({"max_batches": 10_001}, "--max-batches"),
        )
        for options, expected_message in cases:
            with self.subTest(options=options):
                with self.assertRaisesMessage(CommandError, expected_message):
                    call_command(
                        "cleanup_rate_limit_buckets",
                        stdout=StringIO(),
                        stderr=StringIO(),
                        **options,
                    )

    def test_expiration_field_is_indexed(self):
        self.assertTrue(
            RateLimitBucket._meta.get_field("expires_at").db_index
        )


@skipUnless(connection.vendor == "mysql", "MySQL concurrency coverage runs in CI")
@override_settings(SECRET_KEY="mysql-rate-limit-test-secret")
class MySQLRateLimitConcurrencyTests(TransactionTestCase):
    def test_concurrent_requests_never_admit_more_than_the_limit(self):
        workers = 12
        limit = 5
        barrier = Barrier(workers)

        def attempt():
            close_old_connections()
            try:
                request = RequestFactory().post(
                    "/limited/",
                    REMOTE_ADDR="203.0.113.77",
                )
                barrier.wait(timeout=15)
                response = _rate_limit_response(
                    request,
                    "mysql-concurrent",
                    limit,
                    300,
                )
                return response is None
            finally:
                close_old_connections()

        with patch("Domes.ratelimits.time", return_value=1_700_000_123):
            with ThreadPoolExecutor(max_workers=workers) as executor:
                admitted = list(executor.map(lambda _: attempt(), range(workers)))

        self.assertEqual(sum(admitted), limit)
        bucket = RateLimitBucket.objects.get()
        self.assertEqual(bucket.count, workers)
