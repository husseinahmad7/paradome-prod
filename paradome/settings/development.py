"""Local development settings using SQLite and non-secret defaults."""

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from .base import *  # noqa: E402,F403

DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "development-only-key-never-use-in-production"
) or "development-only-key-never-use-in-production"
ALLOWED_HOSTS = env_list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS", ("localhost", "127.0.0.1", "[::1]")
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")  # noqa: F405
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL") or "http://localhost:8000"
DEMO_ACCOUNT_ENABLED = env_bool("DEMO_ACCOUNT_ENABLED", False)  # noqa: F405
DEMO_USERNAME = os.environ.get("DEMO_USERNAME") or DEMO_USERNAME  # noqa: F405
DEFAULT_FROM_EMAIL = (  # noqa: F405
    os.environ.get("DEFAULT_FROM_EMAIL") or DEFAULT_FROM_EMAIL
)
CONTACT_RECIPIENT = os.environ.get("CONTACT_RECIPIENT") or CONTACT_RECIPIENT  # noqa: F405

STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
