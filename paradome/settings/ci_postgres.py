"""Full application regression against a disposable PostgreSQL CI service.

Only this CI profile permits an unencrypted localhost connection. The Wasmer
profile requires TLS and uses the provider's separate DB_USERNAME variable.
"""
from .ci import *  # noqa: F401,F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "HOST": required_env("DB_HOST"), "PORT": required_env("DB_PORT"),  # noqa: F405
    "NAME": required_env("DB_NAME"), "USER": required_env("DB_USER"),  # noqa: F405
    "PASSWORD": required_env("DB_PASSWORD"),  # noqa: F405
    "CONN_MAX_AGE": 0, "OPTIONS": {"connect_timeout": 10, "sslmode": "disable"},
}}
