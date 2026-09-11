"""Fast, deterministic test settings that never need live credentials."""

from pathlib import Path
from tempfile import gettempdir

from .base import *  # noqa: F401,F403

SECRET_KEY = "test-only-key-never-use-in-production"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": ":memory:",
}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = Path(gettempdir()) / "paradome-test-public-media"
PRIVATE_MEDIA_ROOT = Path(gettempdir()) / "paradome-test-private-media"
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "paradome-tests",
}}
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
