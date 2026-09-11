from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import strip_tags


@override_settings(
    DEFAULT_FROM_EMAIL="portfolio@example.com",
    CONTACT_RECIPIENT="owner@example.com",
)
class PortfolioContactTests(TestCase):
    def setUp(self):
        cache.clear()
        self.feedback_url = reverse("HusseinAh:feedback")
        self.valid_message = {
            "subject": "Platform engineering role",
            "email": "visitor@example.com",
            "content": "I would like to discuss a production engineering role.",
            "website": "",
        }

    def test_contact_email_uses_server_sender_and_visitor_reply_to(self):
        response = self.client.post(self.feedback_url, self.valid_message)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "your message has been sent")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.from_email, "portfolio@example.com")
        self.assertEqual(message.to, ["owner@example.com"])
        self.assertEqual(message.reply_to, ["visitor@example.com"])

    def test_honeypot_returns_success_without_sending_email(self):
        payload = {**self.valid_message, "website": "https://spam.example"}

        response = self.client.post(self.feedback_url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "your message has been sent")
        self.assertEqual(mail.outbox, [])

    def test_content_longer_than_limit_is_rejected(self):
        payload = {**self.valid_message, "content": "x" * 5001}

        response = self.client.post(self.feedback_url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value has at most 5000 characters")
        self.assertEqual(mail.outbox, [])

    def test_contact_endpoint_rejects_unsupported_methods(self):
        response = self.client.put(self.feedback_url)

        self.assertEqual(response.status_code, 405)

    def test_fourth_post_in_an_hour_is_rate_limited(self):
        for _ in range(3):
            response = self.client.post(
                self.feedback_url,
                self.valid_message,
                REMOTE_ADDR="203.0.113.44",
            )
            self.assertEqual(response.status_code, 200)

        response = self.client.post(
            self.feedback_url,
            self.valid_message,
            REMOTE_ADDR="203.0.113.44",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 3)

    def test_feedback_form_has_one_htmx_post_and_correct_swap_value(self):
        response = self.client.get(self.feedback_url)
        html = response.content.decode()

        self.assertEqual(html.count("hx-post="), 1)
        self.assertIn('hx-swap="outerHTML"', html)


class PortfolioPageTests(TestCase):
    def test_featured_projects_and_demo_action_are_rendered(self):
        response = self.client.get(reverse("HusseinAh:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "https://husseinahmad7.github.io/dealer-service-360/",
        )
        self.assertContains(
            response,
            "https://github.com/husseinahmad7/dealer-service-360/",
        )
        self.assertContains(
            response,
            "https://husseinahmad7.github.io/schooms/",
        )
        self.assertContains(response, "ForgeEdu")
        self.assertContains(response, reverse("users:demo_login"))

        visible_text = strip_tags(response.content.decode())
        self.assertNotIn("Schooms", visible_text)

    def test_portfolio_does_not_load_bootstrap_or_google_fonts(self):
        response = self.client.get(reverse("HusseinAh:home"))
        html = response.content.decode()

        self.assertNotIn("bootstrap", html.lower())
        self.assertNotIn("fonts.googleapis.com", html)
