"""The template-page failure only occurs when WSGI emits cookie headers."""
from io import BytesIO
from unittest.mock import Mock

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.core.handlers.wsgi import WSGIHandler

from .wasmer_wsgi import normalize_cookie_headers


class CookieHeaderCompatibilityTests(SimpleTestCase):
    def test_real_django_cookie_headers_preserve_security_and_remain_separate(self):
        response = HttpResponse("ready")
        for name in ("csrftoken", "sessionid"):
            response.set_cookie(name, "example", secure=True, httponly=True, samesite="Lax")
        handler = WSGIHandler()
        handler.get_response = Mock(return_value=response)
        captured = Mock(return_value=BytesIO().write)
        environ = RequestFactory().get("/").environ
        body = normalize_cookie_headers(handler)(environ, captured)
        self.assertEqual(b"".join(body), b"ready")
        headers = captured.call_args.args[1]
        cookies = [value for name, value in headers if name.lower() == "set-cookie"]
        self.assertEqual(len(cookies), 2)
        for cookie in cookies:
            self.assertRegex(cookie, r"^[^\s]+.*[^\s]$")
            self.assertIn("Secure", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Lax", cookie)
        self.assertTrue(cookies[0].startswith("csrftoken="))
        self.assertTrue(cookies[1].startswith("sessionid="))

    def test_write_callable_exc_info_and_streaming_iterator_are_preserved(self):
        exception = (ValueError, ValueError("retry"), None)
        stream = iter([b"part one", b"part two"])
        writer = Mock()
        captured = Mock(return_value=writer)

        def handler(environ, start_response):
            self.assertIs(start_response("200 OK", [("Set-Cookie", " \tx=1; Secure\t "),
                                                   ("X-Example", "keep value")], exception), writer)
            return stream

        self.assertIs(normalize_cookie_headers(handler)({}, captured), stream)
        captured.assert_called_once_with("200 OK", [("Set-Cookie", "x=1; Secure"),
                                                    ("X-Example", "keep value")], exception)
