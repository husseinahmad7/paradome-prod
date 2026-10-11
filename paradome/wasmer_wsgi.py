"""Django WSGI with HTTP-safe cookie serialization for Uvicorn's adapter."""
import os

from django.core.wsgi import get_wsgi_application


def normalize_cookie_headers(wsgi_application):
    # Django's WSGI handler uses Morsel.output(header=""), which prefixes a
    # space. Uvicorn's WSGI adapter passes it unchanged to h11, which rejects
    # leading OWS. Preserve separate cookies and every cookie attribute.
    def application(environ, start_response):
        def start(status, headers, exc_info=None):
            headers = [
                (name, value.strip(" \t") if name.lower() == "set-cookie" else value)
                for name, value in headers
            ]
            return start_response(status, headers, exc_info)

        return wsgi_application(environ, start)

    return application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paradome.settings.wasmer")
app = normalize_cookie_headers(get_wsgi_application())
application = app
