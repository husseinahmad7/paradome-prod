"""Production settings with fail-closed environment validation."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_env_file = os.environ.get("PARADOME_ENV_FILE")
if _env_file:
    env_path = Path(_env_file).expanduser().resolve()
    if not env_path.is_file():
        raise RuntimeError("PARADOME_ENV_FILE does not point to a readable file")
    project_root = Path(__file__).resolve().parents[2]
    if env_path.is_relative_to(project_root):
        raise RuntimeError("PARADOME_ENV_FILE must be stored outside the checkout")
    if os.name == "posix" and env_path.stat().st_mode & 0o077:
        raise RuntimeError("PARADOME_ENV_FILE permissions must be 0600 or stricter")
    load_dotenv(env_path, override=False)

from .base import *  # noqa: E402,F403

DEBUG = False
SECRET_KEY = required_env("DJANGO_SECRET_KEY")  # noqa: F405
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")  # noqa: F405
if not ALLOWED_HOSTS:
    raise RuntimeError("Required environment variable DJANGO_ALLOWED_HOSTS is not set")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405
if not CSRF_TRUSTED_ORIGINS:
    raise RuntimeError(
        "Required environment variable DJANGO_CSRF_TRUSTED_ORIGINS is not set"
    )
if any(not origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):
    raise RuntimeError("Every production CSRF trusted origin must use HTTPS")
PUBLIC_SITE_URL = required_env("PUBLIC_SITE_URL").rstrip("/")  # noqa: F405
if not PUBLIC_SITE_URL.startswith("https://"):
    raise RuntimeError("PUBLIC_SITE_URL must use HTTPS in production")

DATABASES = {"default": {
    "ENGINE": "django.db.backends.mysql",
    "HOST": required_env("DB_HOST"),  # noqa: F405
    "PORT": env_int("DB_PORT", 3306),  # noqa: F405
    "NAME": required_env("DB_NAME"),  # noqa: F405
    "USER": required_env("DB_USER"),  # noqa: F405
    "PASSWORD": required_env("DB_PASSWORD"),  # noqa: F405
    "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),  # noqa: F405
    "CONN_HEALTH_CHECKS": True,
    "OPTIONS": {
        "charset": "utf8mb4",
        "init_command": (
            "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,"
            "NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'"
        ),
        "isolation_level": "read committed",
        "connect_timeout": env_int("DB_CONNECT_TIMEOUT", 10),  # noqa: F405
    },
}}

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required_env("EMAIL_HOST")  # noqa: F405
EMAIL_PORT = env_int("EMAIL_PORT", 587)  # noqa: F405
EMAIL_HOST_USER = required_env("EMAIL_HOST_USER")  # noqa: F405
EMAIL_HOST_PASSWORD = required_env("EMAIL_HOST_PASSWORD")  # noqa: F405
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)  # noqa: F405
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)  # noqa: F405
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled")
DEFAULT_FROM_EMAIL = required_env("DEFAULT_FROM_EMAIL")  # noqa: F405
SERVER_EMAIL = os.environ.get("SERVER_EMAIL") or DEFAULT_FROM_EMAIL
CONTACT_RECIPIENT = required_env("CONTACT_RECIPIENT")  # noqa: F405

PUSHER_APP_ID = required_env("PUSHER_APP_ID")  # noqa: F405
PUSHER_KEY = required_env("PUSHER_KEY")  # noqa: F405
PUSHER_SECRET = required_env("PUSHER_SECRET")  # noqa: F405
PUSHER_CLUSTER = required_env("PUSHER_CLUSTER")  # noqa: F405
PUSHER_SSL = True

DEMO_ACCOUNT_ENABLED = required_env_bool("DEMO_ACCOUNT_ENABLED")  # noqa: F405
DEMO_USERNAME = required_env("DEMO_USERNAME")  # noqa: F405
DEMO_DOME_SLUG = required_env("DEMO_DOME_SLUG")  # noqa: F405
_private_media_path = Path(required_env("PRIVATE_MEDIA_ROOT"))  # noqa: F405
if not _private_media_path.is_absolute():
    raise RuntimeError("PRIVATE_MEDIA_ROOT must be an absolute path")
PRIVATE_MEDIA_ROOT = _private_media_path.resolve()
if PRIVATE_MEDIA_ROOT.is_relative_to(  # noqa: F405
    MEDIA_ROOT.resolve()
) or PRIVATE_MEDIA_ROOT.is_relative_to(STATIC_ROOT.resolve()):  # noqa: F405
    raise RuntimeError("PRIVATE_MEDIA_ROOT cannot be inside a publicly served directory")

# A database-backed cache is shared by every Gunicorn worker and therefore
# provides a consistent backend for django-ratelimit.
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
    "LOCATION": os.environ.get("CACHE_TABLE", "paradome_cache"),
    "TIMEOUT": env_int("CACHE_TIMEOUT", 300),  # noqa: F405
    "OPTIONS": {"MAX_ENTRIES": env_int("CACHE_MAX_ENTRIES", 10_000)},  # noqa: F405
}}

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
