"""MySQL regression for expired-run collection racing an in-flight source write."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections, connection, connections
from django.db.models.deletion import Collector
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from . import services
from .models import ConsumerReceipt, LabRun, OutboxEvent, Submission, Trace


def isolated_connection(callback):
    close_old_connections()
    try:
        return callback()
    finally:
        connections.close_all()


@skipUnless(connection.vendor == "mysql", "Requires real MySQL locks and foreign keys.")
class LabExpiredCleanupConcurrencyTests(TransactionTestCase):
    def test_create_run_collects_expired_children_after_inflight_source_commit(self):
        # Establish ownership before the race; owner initialization has its own
        # regression tests using independently preloaded session stores.
        session = SessionStore()
        session[services.SESSION_OWNER_KEY] = "cleanup-owner-" + uuid.uuid4().hex
        session.save()

        def owner_request():
            request = RequestFactory().post("/engineering/runs/")
            request.user = AnonymousUser()
            request.session = SessionStore(session_key=session.session_key)
            request.session.get(services.SESSION_OWNER_KEY)
            return request

        run = services.create_run(owner_request())
        before = timezone.now()
        LabRun.objects.filter(pk=run.id).update(expires_at=before + timedelta(seconds=1))
        cleanup_request = owner_request()
        writer_paused, resume_writer, cleanup_boundary = Event(), Event(), Event()
        original_create = Submission.objects.create
        original_collect = Collector.collect

        def pause_source_write(*args, **kwargs):
            # submit already holds the root lock and has passed the expiry check.
            writer_paused.set()
            if not resume_writer.wait(timeout=15):
                raise AssertionError("Cleanup never reached the locked root.")
            return original_create(*args, **kwargs)

        def observe_collection(collector, objects, *args, **kwargs):
            result = original_collect(collector, objects, *args, **kwargs)
            if getattr(objects, "model", None) is LabRun:
                # The old ordering collected no children before waiting on the
                # root DELETE. Release the writer only after that stale snapshot.
                cleanup_boundary.set()
            return result

        def observe_root_lock(execute, sql, params, many, context):
            if "FOR UPDATE" in sql.upper() and LabRun._meta.db_table.upper() in sql.upper():
                # The fixed ordering waits on this root lock before collecting.
                # Signal before the blocking query so the writer may commit.
                cleanup_boundary.set()
            return execute(sql, params, many, context)

        def write_source():
            submission, created = services.submit(
                run, uuid.uuid4(), "The export button returns an error.",
                {"status": "unavailable"},
            )
            return submission.id, created

        def cleanup():
            with connection.execute_wrapper(observe_root_lock):
                return services.create_run(cleanup_request)

        with patch("engineering.services.timezone.now", return_value=before) as clock, \
                patch.object(Submission.objects, "create", side_effect=pause_source_write), \
                patch.object(Collector, "collect", new=observe_collection), \
                ThreadPoolExecutor(max_workers=2) as pool:
            source = pool.submit(isolated_connection, write_source)
            try:
                self.assertTrue(writer_paused.wait(timeout=15), "Source did not acquire its root lock.")
                clock.return_value = before + timedelta(seconds=2)
                replacement = pool.submit(isolated_connection, cleanup)
                self.assertTrue(cleanup_boundary.wait(timeout=15), "Cleanup did not reach collection or the root lock.")
            finally:
                resume_writer.set()
            submission_id, created = source.result(timeout=30)
            replacement_run = replacement.result(timeout=30)

        self.assertTrue(created)
        self.assertFalse(LabRun.objects.filter(pk=run.id).exists())
        self.assertFalse(Submission.objects.filter(pk=submission_id).exists())
        self.assertEqual(OutboxEvent.objects.count(), 0)
        self.assertEqual(ConsumerReceipt.objects.count(), 0)
        self.assertEqual(Trace.objects.count(), 0)
        self.assertNotEqual(replacement_run.id, run.id)
        self.assertEqual(replacement_run.owner_hash, run.owner_hash)
        self.assertEqual(LabRun.objects.filter(owner_hash=run.owner_hash).count(), 1)
