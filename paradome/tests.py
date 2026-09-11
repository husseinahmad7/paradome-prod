import re
from unittest.mock import patch
from xml.etree import ElementTree

from django.db import connections
from django.test import TestCase


class HealthAndSecurityHeadersTests(TestCase):
    def test_health_reports_database_readiness_without_caching(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_health_failure_does_not_disclose_exception_details(self):
        connection = connections["default"]
        with patch.object(connection, "cursor", side_effect=RuntimeError("sensitive detail")):
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "sensitive detail", status_code=503)

    def test_dynamic_responses_include_security_headers(self):
        response = self.client.get("/health/")

        for header in (
            "Content-Security-Policy",
            "Permissions-Policy",
            "Referrer-Policy",
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Cross-Origin-Opener-Policy",
            "Cross-Origin-Resource-Policy",
        ):
            self.assertIn(header, response.headers)

    def test_health_rejects_non_get_requests(self):
        response = self.client.post("/health/")

        self.assertEqual(response.status_code, 405)

    def test_portfolio_inline_data_uses_enforced_csp_nonce(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        nonce_match = re.search(rb'<script[^>]+nonce="([^"]+)"', response.content)
        self.assertIsNotNone(nonce_match)
        script_directive = next(
            directive.strip()
            for directive in response.headers["Content-Security-Policy"].split(";")
            if directive.strip().startswith("script-src ")
        )
        nonce = nonce_match.group(1).decode("ascii")
        self.assertIn(f"'nonce-{nonce}'", script_directive)
        self.assertNotIn("'unsafe-inline'", script_directive)


class SitemapTests(TestCase):
    def test_sitemap_includes_portfolio_home_but_not_feedback_form(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.content)
        namespace = {"sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = {
            location.text
            for location in root.findall("sitemap:url/sitemap:loc", namespace)
        }
        self.assertIn("http://testserver/", locations)
        self.assertNotIn("http://testserver/feedback/", locations)
