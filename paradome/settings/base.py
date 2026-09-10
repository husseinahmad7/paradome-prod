"""Shared settings that are safe to import without production secrets."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from csp.constants import NONE, NONCE, SELF

mimetypes.add_type("text/css", ".css", True)
BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"0", "1", "false", "true", "no", "yes", "off", "on"}:
        raise RuntimeError(f"{name} must be a boolean")
    return normalized in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def env_list(name: str, default: tuple[str, ...] = ()) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def required_env_bool(name: str) -> bool:
    required_env(name)
    return env_bool(name)


SECRET_KEY = "development-only-key-never-use-in-production"
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
CSRF_TRUSTED_ORIGINS: list[str] = []
PUBLIC_SITE_URL = "http://localhost:8000"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "HusseinAh",
    "users",
    "posts",
    "messages",
    "notify",
    "Domes",
    "Chat",
    "django_filters",
    "django_prose_editor",
    "crispy_forms",
    "crispy_bulma",
    "csp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "paradome.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "paradome.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "csp.context_processors.nonce",
            "messages.views.check_directs",
            "notify.views.CountNotifications",
        ],
        "libraries": {"csp": "csp.templatetags.csp"},
    },
}]

WSGI_APPLICATION = "paradome.wsgi.application"
ASGI_APPLICATION = "paradome.asgi.application"
DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / "db.sqlite3",
}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Damascus"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static_files"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = Path(os.environ.get("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media"))
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}
WHITENOISE_MAX_AGE = 31_536_000
WHITENOISE_KEEP_ONLY_HASHED_FILES = True
WHITENOISE_ALLOW_ALL_ORIGINS = False

CRISPY_TEMPLATE_PACK = "bulma"
CRISPY_ALLOWED_TEMPLATE_PACKS = ("bulma",)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_REDIRECT_URL = "users:index"
LOGIN_URL = "users:login"
SESSION_COOKIE_AGE = 86_400
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = "webmaster@localhost"
SERVER_EMAIL = "server@localhost"
CONTACT_RECIPIENT = "webmaster@localhost"

PUSHER_APP_ID = ""
PUSHER_KEY = ""
PUSHER_SECRET = ""
PUSHER_CLUSTER = ""
PUSHER_SSL = True
DEMO_ACCOUNT_ENABLED = False
DEMO_USERNAME = "paradome-demo"
DEMO_DOME_SLUG = "demo"

CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "paradome-development",
    "TIMEOUT": 300,
}}
RATELIMIT_USE_CACHE = "default"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), "
    "publickey-credentials-get=(), usb=()"
)

# Every repository-owned inline script is nonced; executable inline script and
# event-handler attributes are therefore rejected by the production policy.
CONTENT_SECURITY_POLICY = {"DIRECTIVES": {
    "default-src": [SELF],
    "base-uri": [SELF],
    "object-src": [NONE],
    "frame-ancestors": [NONE],
    "form-action": [SELF],
    "script-src": [
        SELF,
        NONCE,
        "https://js.pusher.com",
    ],
    "style-src": [
        SELF,
        "'unsafe-inline'",
        "https://cdn.jsdelivr.net",
    ],
    "font-src": [SELF],
    "img-src": [SELF, "data:", "https://bulma.io"],
    "connect-src": [SELF, "https://*.pusher.com", "wss://*.pusher.com"],
    "media-src": [SELF],
    "worker-src": [SELF, "blob:"],
    "manifest-src": [SELF],
}}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "production": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "production",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
