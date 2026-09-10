from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Message


class DirectMessageModelTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user("sender", password="x")
        self.recipient = User.objects.create_user("recipient", password="x")

    def test_send_message_writes_both_conversation_copies_atomically(self):
        sent = Message.send_message(self.sender, self.recipient, " Hello ")
        self.assertEqual(sent.body, "Hello")
        self.assertEqual(Message.objects.count(), 2)
        inbox_copy = Message.objects.get(user=self.recipient)
        self.assertEqual(inbox_copy.sender, self.sender)
        self.assertEqual(inbox_copy.recipient, self.sender)
        self.assertFalse(inbox_copy.is_read)

    def test_invalid_message_writes_nothing(self):
        with self.assertRaises(ValidationError):
            Message.send_message(self.sender, self.recipient, "   ")
        self.assertEqual(Message.objects.count(), 0)

    def test_conversation_summary_uses_counterpart_and_unread_count(self):
        Message.send_message(self.sender, self.recipient, "First")
        Message.send_message(self.recipient, self.sender, "Reply")
        summaries = Message.get_messages(self.sender)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["user"], self.recipient)
        self.assertEqual(summaries[0]["unread"], 1)


class DirectMessageSecurityTests(TestCase):
    def setUp(self):
        self.sender = User.objects.create_user("sender", password="x")
        self.recipient = User.objects.create_user("recipient", password="x")
        self.other = User.objects.create_user("other", password="x")

    def test_url_recipient_cannot_be_overridden_by_form_data(self):
        self.client.force_login(self.sender)
        response = self.client.post(
            reverse("messages:directs", args=[self.recipient.username]),
            {"body": "Hello", "to_user": self.other.username},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Message.objects.filter(sender=self.sender, user=self.recipient).exists()
        )
        self.assertFalse(Message.objects.filter(user=self.other).exists())

    def test_demo_accounts_cannot_send_or_receive_direct_messages(self):
        group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo")
        demo.groups.add(group)
        with self.assertRaises(ValidationError):
            Message.send_message(demo, self.recipient, "No")
        with self.assertRaises(ValidationError):
            Message.send_message(self.sender, demo, "No")

        self.client.force_login(demo)
        self.assertEqual(self.client.get(reverse("messages:inbox")).status_code, 403)
        self.client.force_login(self.sender)
        self.assertEqual(
            self.client.get(
                reverse("messages:directs", args=[demo.username])
            ).status_code,
            404,
        )

    def test_message_body_length_is_validated(self):
        self.client.force_login(self.sender)
        response = self.client.post(
            reverse("messages:directs", args=[self.recipient.username]),
            {"body": "x" * 1001},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Message.objects.exists())

    def test_read_receipt_is_a_post_only_explicit_mutation(self):
        Message.send_message(self.recipient, self.sender, "Unread")
        inbox_copy = Message.objects.get(
            user=self.sender,
            recipient=self.recipient,
            is_read=False,
        )
        self.client.force_login(self.sender)
        conversation_url = reverse(
            "messages:directs", args=[self.recipient.username]
        )
        mark_url = reverse("messages:mark-read", args=[self.recipient.username])

        self.assertEqual(self.client.get(conversation_url).status_code, 200)
        inbox_copy.refresh_from_db()
        self.assertFalse(inbox_copy.is_read)
        self.assertEqual(self.client.get(mark_url).status_code, 405)
        self.assertEqual(self.client.post(mark_url).status_code, 302)
        inbox_copy.refresh_from_db()
        self.assertTrue(inbox_copy.is_read)
