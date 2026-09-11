"""Database-backed rate limiting for authentication and content writes."""

import hashlib
import hmac
import json
import logging
import unicodedata
from functools import wraps
from time import time

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.http import HttpResponse

from .models import RateLimitBucket


logger = logging.getLogger(__name__)
_SUBJECT_DOMAIN = b"paradome.rate-limit.subject.v1\x00"


def _subject_hash(scope, window_seconds, kind, value):
    """Return a domain-separated HMAC without persisting raw identifiers."""

    payload = json.dumps(
        [str(scope), int(window_seconds), str(kind), str(value)],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    key = str(settings.SECRET_KEY).encode("utf-8")
    return hmac.new(key, _SUBJECT_DOMAIN + payload, hashlib.sha256).hexdigest()


def _client_ip_identity(request, scope, window_seconds):
    """Use only the server-derived address; never trust client proxy headers."""

    return _subject_hash(
        scope,
        window_seconds,
        "ip",
        str(request.META.get("REMOTE_ADDR", "unknown")),
    )


def _submitted_account_identity(request, scope, window_seconds):
    """Normalize and hash a submitted account name without checking existence."""

    submitted = request.POST.get("username", "")
    normalized = unicodedata.normalize("NFKC", str(submitted)).strip().casefold()
    if not normalized:
        return None
    return _subject_hash(scope, window_seconds, "account", normalized)


def _rate_limit_identities(request, scope, window_seconds, identity_modes):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        return (_subject_hash(scope, window_seconds, "user", user.pk),)

    identities = []
    for mode in identity_modes:
        if mode == "ip":
            identity = _client_ip_identity(request, scope, window_seconds)
        elif mode == "account":
            identity = _submitted_account_identity(request, scope, window_seconds)
        else:
            raise ValueError(f"Unsupported rate-limit identity mode: {mode}")
        if identity and identity not in identities:
            identities.append(identity)
    return tuple(identities)


def _increment_rate_limit_bucket(subject_hash, window_start):
    """Atomically create or increment one fixed-window bucket."""

    for attempt in range(2):
        try:
            with transaction.atomic():
                updated = RateLimitBucket.objects.filter(
                    subject_hash=subject_hash,
                    window_start=window_start,
                ).update(count=F("count") + 1)

                if updated:
                    bucket = (
                        RateLimitBucket.objects.select_for_update()
                        .only("count")
                        .get(
                            subject_hash=subject_hash,
                            window_start=window_start,
                        )
                    )
                    count = bucket.count
                else:
                    bucket = RateLimitBucket.objects.create(
                        subject_hash=subject_hash,
                        window_start=window_start,
                        count=1,
                    )
                    count = 1

                RateLimitBucket.objects.filter(
                    subject_hash=subject_hash,
                    window_start__lt=window_start,
                ).exclude(pk=bucket.pk).delete()
                return count
        except IntegrityError:
            if attempt:
                raise

    raise RuntimeError("Unreachable rate-limit counter state")


def _too_many_requests(retry_after):
    response = HttpResponse("Too many requests", status=429)
    response.headers["Retry-After"] = str(retry_after)
    response.headers["Cache-Control"] = "no-store"
    return response


def _rate_limit_response(
    request,
    scope,
    limit,
    window_seconds,
    *,
    authenticated_only=False,
    identity_modes=("ip",),
):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None

    user = getattr(request, "user", None)
    if authenticated_only and not getattr(user, "is_authenticated", False):
        return None

    now = int(time())
    window_start = now - (now % window_seconds)
    retry_after = window_start + window_seconds - now
    exceeded = False
    for subject_hash in _rate_limit_identities(
        request,
        scope,
        window_seconds,
        identity_modes,
    ):
        try:
            count = _increment_rate_limit_bucket(subject_hash, window_start)
        except DatabaseError:
            logger.exception("Rate-limit counter failure for scope %s", scope)
            return _too_many_requests(retry_after)
        exceeded = exceeded or count > limit

    if not exceeded:
        return None
    return _too_many_requests(retry_after)


def rate_limit(
    scope,
    limit=10,
    window_seconds=60,
    *,
    authenticated_only=False,
    identity_modes=("ip",),
):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            limited = _rate_limit_response(
                request,
                scope,
                limit=limit,
                window_seconds=window_seconds,
                authenticated_only=authenticated_only,
                identity_modes=identity_modes,
            )
            return limited or view(request, *args, **kwargs)

        return wrapped

    return decorator


def user_write_rate_limit(scope, limit=30, window_seconds=60):
    return rate_limit(
        scope,
        limit=limit,
        window_seconds=window_seconds,
        authenticated_only=True,
    )


class UserWriteRateLimitMixin:
    rate_limit_scope = "content"
    rate_limit_count = 30
    rate_limit_window_seconds = 60

    def dispatch(self, request, *args, **kwargs):
        limited = _rate_limit_response(
            request,
            self.rate_limit_scope,
            limit=self.rate_limit_count,
            window_seconds=self.rate_limit_window_seconds,
            authenticated_only=True,
        )
        if limited is not None:
            return limited
        return super().dispatch(request, *args, **kwargs)


class AnonymousWriteRateLimitMixin:
    rate_limit_scope = "authentication"
    rate_limit_count = 10
    rate_limit_window_seconds = 300
    rate_limit_identity_modes = ("ip",)

    def dispatch(self, request, *args, **kwargs):
        limited = _rate_limit_response(
            request,
            self.rate_limit_scope,
            limit=self.rate_limit_count,
            window_seconds=self.rate_limit_window_seconds,
            identity_modes=self.rate_limit_identity_modes,
        )
        if limited is not None:
            return limited
        return super().dispatch(request, *args, **kwargs)
