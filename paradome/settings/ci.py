"""CI settings: production's MySQL schema with isolated test services."""

from .production import *  # noqa: F401,F403

# DATABASES intentionally remains exactly the production MySQL configuration.
# CI supplies credentials for its disposable MySQL service.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    "LOCATION": "paradome-ci-tests",
}}
RATELIMIT_USE_CACHE = "default"

# Test clients make in-process HTTP requests; HTTPS enforcement itself is
# validated separately with the unmodified production settings module.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0

STORAGES = {**STORAGES, "staticfiles": {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}}
