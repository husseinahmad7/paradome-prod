"""Independent Wasmer demo; fail closed on hosts, secrets and storage."""
import os
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = required_env("DJANGO_SECRET_KEY")  # noqa: F405
if len(SECRET_KEY) < 50:
    raise RuntimeError("Wasmer DJANGO_SECRET_KEY must contain at least 50 characters")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS or any("*" in h or h.startswith(".") or "/" in h or ":" in h for h in ALLOWED_HOSTS):
    raise RuntimeError("Configure exact Wasmer hostnames; wildcards are forbidden")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405
PUBLIC_SITE_URL = required_env("PUBLIC_SITE_URL").rstrip("/")  # noqa: F405
for origin in [PUBLIC_SITE_URL, *CSRF_TRUSTED_ORIGINS]:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RuntimeError("Wasmer origins must be exact HTTPS origins matching allowed hosts")
if not CSRF_TRUSTED_ORIGINS or PUBLIC_SITE_URL not in CSRF_TRUSTED_ORIGINS:
    raise RuntimeError("Include the exact public origin in CSRF_TRUSTED_ORIGINS")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "HOST": required_env("DB_HOST"), "PORT": required_env("DB_PORT"),  # noqa: F405
    "NAME": required_env("DB_NAME"), "USER": required_env("DB_USERNAME"), "PASSWORD": required_env("DB_PASSWORD"),  # noqa: F405
    "CONN_MAX_AGE": 30, "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {"connect_timeout": 10,
                "sslmode": "verify-full" if os.environ.get("DB_SSL_CA") else "require",
                **({"sslrootcert": os.environ["DB_SSL_CA"]} if os.environ.get("DB_SSL_CA") else {})},
}}
private_path = os.environ.get("PRIVATE_MEDIA_ROOT", "/data/private-media")
private_posix = PurePosixPath(private_path)
if "\\" in private_path or ".." in private_posix.parts or not private_posix.is_absolute() or not private_posix.is_relative_to(PurePosixPath("/data")):
    raise RuntimeError("Wasmer private media must live under the persistent /data volume")
PRIVATE_MEDIA_ROOT = Path(private_path)
WSGI_APPLICATION = "paradome.wasmer_wsgi.app"
RICH_TEXT_SANITIZER = "ammonia-wasi"
CONTACT_FORM_ENABLED = False
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
CHAT_REALTIME_ENABLED = False
PUSHER_APP_ID = PUSHER_KEY = PUSHER_SECRET = PUSHER_CLUSTER = ""
DEMO_ACCOUNT_ENABLED = True
DEMO_USERNAME = "paradome-wasmer-guest"
SESSION_PAGES_NOSTORE = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "paradome_wasmer_cache", "TIMEOUT": 300, "OPTIONS": {"MAX_ENTRIES": 1000}}}
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_PRELOAD = True
