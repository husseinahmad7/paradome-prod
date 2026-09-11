"""Cache-backed rate limiting for authentication and content writes."""

import hashlib
import time
import unicodedata
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


def _hashed_identity(kind, value):
    """Return a namespaced, privacy-safe cache identity."""

    raw = f"{kind}:{value}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{kind}-{digest}"


def _client_ip_identity(request):
    """Use only the server-derived address; never trust client proxy headers."""

    return _hashed_identity("ip", str(request.META.get("REMOTE_ADDR", "unknown")))


def _submitted_account_identity(request):
    """Normalize and hash a submitted account name without checking existence."""

    submitted = request.POST.get("username", "")
    normalized = unicodedata.normalize("NFKC", str(submitted)).strip().casefold()
    if not normalized:
        return None
    return _hashed_identity("account", normalized)


def _rate_limit_identities(request, identity_modes):
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        return (f"user-{user.pk}",)

    identities = []
    for mode in identity_modes:
        if mode == "ip":
            identity = _client_ip_identity(request)
        elif mode == "account":
            identity = _submitted_account_identity(request)
        else:
            raise ValueError(f"Unsupported rate-limit identity mode: {mode}")
        if identity and identity not in identities:
            identities.append(identity)
    return tuple(identities)


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

    bucket = int(time.time() // window_seconds)
    exceeded = False
    for identity in _rate_limit_identities(request, identity_modes):
        key = f"rate:{scope}:{identity}:{bucket}"
        if cache.add(key, 1, timeout=window_seconds + 1):
            count = 1
        else:
            try:
                count = cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window_seconds + 1)
                count = 1
        exceeded = exceeded or count > limit

    if not exceeded:
        return None

    retry_after = window_seconds - (int(time.time()) % window_seconds)
    response = HttpResponse("Too many requests", status=429)
    response.headers["Retry-After"] = str(retry_after)
    response.headers["Cache-Control"] = "no-store"
    return response


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
