"""Response hardening not covered directly by Django settings."""

from django.conf import settings


class SecurityHeadersMiddleware:
    """Attach browser capability and cross-origin policies."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.path == "/health/":
            response.headers["Cache-Control"] = "no-store"
        return response
