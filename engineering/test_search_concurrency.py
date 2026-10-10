from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from . import search
from .models import LabRun, SearchObservation


@skipUnless(connection.vendor == "mysql", "Requires real MySQL row locks.")
class SearchTelemetryConcurrencyTests(TransactionTestCase):
    def test_two_connections_cannot_exceed_the_observation_cap(self):
        run = LabRun.objects.create(owner_hash="a" * 64, slot=0, expires_at=timezone.now() + timedelta(hours=1))
        result = search.retrieve("CSRF token")
        for _ in range(39):
            search.record_observation(run, result, {})
        barrier = Barrier(2)
        def write():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                search.record_observation(run, result, {})
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(write) for _ in range(2)]
            for future in futures:
                future.result(timeout=20)
        self.assertEqual(SearchObservation.objects.filter(run=run).count(), 40)
