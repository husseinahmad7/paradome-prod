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
        import nh3
        from PIL import Image
        import MySQLdb
        cleaned = nh3.clean('<p>allowed<img src=x onerror=alert(1)><script>alert(2)</script></p>')
        if "onerror" in cleaned or "<script" in cleaned or "allowed" not in cleaned:
            raise CommandError("Sanitizer compatibility gate failed")
        encoded = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(encoded, format="PNG")
        encoded.seek(0)
        Image.open(encoded).verify()
        if connection.vendor != "mysql":
            raise CommandError("Wasmer must use managed MySQL; SQLite is not a compatible substitute")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            cipher = cursor.fetchone()
            if not cipher or not cipher[1]:
                raise CommandError("Managed database TLS is not active")
        settings.PRIVATE_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        probe = settings.PRIVATE_MEDIA_ROOT / ("compatibility-" + uuid.uuid4().hex)
        try:
            probe.write_bytes(b"private-volume-probe")
            if probe.read_bytes() != b"private-volume-probe":
                raise CommandError("Private volume round trip failed")
        finally:
            probe.unlink(missing_ok=True)
        self.stdout.write(json.dumps({"native_sanitizer": "passed", "image_codec": "passed", "mysql_driver": "passed", "database_tls": "passed", "private_volume_write": "passed", "restart_persistence": "requires separate release test"}))
