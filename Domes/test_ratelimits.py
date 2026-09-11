from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import DatabaseError, close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings

from .models import RateLimitBucket
from .ratelimits import _rate_limit_identities, _rate_limit_response


@override_settings(SECRET_KEY="rate-limit-test-secret")
class DatabaseRateLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def request(self, *, ip="203.0.113.10", username=""):
        return self.factory.post(
            "/limited/",
            {"username": username},
            REMOTE_ADDR=ip,
        )

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
        self.assertEqual(bucket.count, 3)

    @patch("Domes.ratelimits.time", return_value=181.25)
    def test_increment_removes_only_older_buckets_for_same_subject(self, _now):
        request = self.request()
        subject_hash = _rate_limit_identities(
            request,
            "cleanup",
            60,
            ("ip",),
        )[0]
        RateLimitBucket.objects.create(
            subject_hash=subject_hash,
            window_start=60,
            count=2,
        )
        other_subject = "f" * 64
        RateLimitBucket.objects.create(
            subject_hash=other_subject,
            window_start=60,
            count=1,
        )

        self.assertIsNone(_rate_limit_response(request, "cleanup", 5, 60))

        self.assertEqual(
            list(
                RateLimitBucket.objects.filter(subject_hash=subject_hash)
                .values_list("window_start", "count")
            ),
            [(180, 1)],
        )
        self.assertTrue(
            RateLimitBucket.objects.filter(subject_hash=other_subject).exists()
        )

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
