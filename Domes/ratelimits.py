"""Cache-backed rate limiting for authentication and content writes."""

import hashlib
import time
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


def _client_identity(request):
    """Use server-derived address plus account name without trusting proxy headers."""

    address = request.META.get("REMOTE_ADDR", "unknown")
    username = request.POST.get("username", "") if request.method == "POST" else ""
    raw = f"{address}:{username.casefold()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _rate_limit_response(
    request,
    scope,
    limit,
    window_seconds,
    *,
    authenticated_only=False,
):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None

    user = getattr(request, "user", None)
    if authenticated_only and not getattr(user, "is_authenticated", False):
        return None

    identity = (
        f"user-{user.pk}"
        if getattr(user, "is_authenticated", False)
        else f"client-{_client_identity(request)}"
    )
    bucket = int(time.time() // window_seconds)
    key = f"rate:{scope}:{identity}:{bucket}"
    if cache.add(key, 1, timeout=window_seconds + 1):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds + 1)
            count = 1

    if count <= limit:
        return None

    retry_after = window_seconds - (int(time.time()) % window_seconds)
    response = HttpResponse("Too many requests", status=429)
    response.headers["Retry-After"] = str(retry_after)
    response.headers["Cache-Control"] = "no-store"
    return response


def rate_limit(scope, limit=10, window_seconds=60, *, authenticated_only=False):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            limited = _rate_limit_response(
                request,
                scope,
                limit=limit,
                window_seconds=window_seconds,
                authenticated_only=authenticated_only,
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

    def dispatch(self, request, *args, **kwargs):
        limited = _rate_limit_response(
            request,
            self.rate_limit_scope,
            limit=self.rate_limit_count,
            window_seconds=self.rate_limit_window_seconds,
        )
        if limited is not None:
            return limited
        return super().dispatch(request, *args, **kwargs)
