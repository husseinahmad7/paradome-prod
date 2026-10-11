"""A real runtime gate: native imports, sanitizer behavior, DB TLS, file writes."""
import io
import json
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Check required native packages and managed database in the actual Wasmer runtime."

    def handle(self, *args, **options):
        from PIL import Image
        import psycopg
        from posts.sanitizers import sanitize_rich_text
        cleaned = sanitize_rich_text('<p>allowed<img src=x onerror=alert(1)><script>alert(2)</script></p>')
        if "onerror" in cleaned or "<script" in cleaned or "allowed" not in cleaned:
            raise CommandError("Sanitizer compatibility gate failed")
        encoded = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(encoded, format="PNG")
        encoded.seek(0)
        Image.open(encoded).verify()
        if connection.vendor != "postgresql":
            raise CommandError("Wasmer must use managed PostgreSQL; SQLite is not a compatible substitute")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            tls = cursor.fetchone()
            if not tls or not tls[0]:
                raise CommandError("Managed database TLS is not active")
        settings.PRIVATE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        probe = settings.PRIVATE_MEDIA_ROOT / ("compatibility-" + uuid.uuid4().hex)
        try:
            probe.write_bytes(b"private-volume-probe")
            if probe.read_bytes() != b"private-volume-probe":
                raise CommandError("Private volume round trip failed")
        finally:
            probe.unlink(missing_ok=True)
        self.stdout.write(json.dumps({"sanitizer": "passed", "image_codec": "passed", "postgres_driver": psycopg.__version__, "database_tls": "passed", "private_volume_write": "passed", "restart_persistence": "requires separate release test"}))
