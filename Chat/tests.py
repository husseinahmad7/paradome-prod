from unittest.mock import Mock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from Domes.models import Category, Dome

from .models import ChatChannel, ChatMessage


def make_dome(owner, *, title="Chat Dome", privacy=1):
    return Dome.objects.create(
        title=title,
        description="Chat security test",
        user=owner,
        privacy=privacy,
        icon=None,
        banner=None,
    )


@override_settings(
    PUSHER_APP_ID="test-app",
    PUSHER_KEY="test-key",
    PUSHER_SECRET="test-secret",
    PUSHER_CLUSTER="test-cluster",
)
class ChatSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x")
        self.member = User.objects.create_user("member", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        self.dome = make_dome(self.owner)
        self.dome.members.add(self.member)
        self.category = Category.objects.create(title="General", Dome=self.dome)
        self.channel = ChatChannel.objects.create(
            title="chat", topic="Topic", category=self.category
        )

    def test_public_dome_chat_requires_explicit_membership(self):
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(reverse("chat:chat-channel", args=[self.channel.pk])).status_code,
            403,
        )
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("chat:chat-channel", args=[self.channel.pk])).status_code,
            200,
        )

    @patch("Chat.views.get_pusher_client")
    def test_private_channel_auth_checks_membership(self, get_client):
        client = Mock()
        client.authenticate.return_value = {"auth": "signed"}
        get_client.return_value = client
        url = reverse("chat:pusher-auth")
        payload = {
            "channel_name": f"private-chat-{self.channel.pk}",
            "socket_id": "123.456",
        }
        self.client.force_login(self.member)
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        client.authenticate.assert_called_once_with(
            channel=payload["channel_name"], socket_id=payload["socket_id"]
        )

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url, payload).status_code, 403)

    def test_private_channel_auth_rejects_forged_name(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chat:pusher-auth"),
            {"channel_name": "public-chat-1", "socket_id": "1.2"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("Chat.views.get_pusher_client")
    def test_message_event_contains_identifiers_only(self, get_client):
        pusher_client = Mock()
        get_client.return_value = pusher_client
        self.client.force_login(self.member)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chat:chat-channel", args=[self.channel.pk]),
                {"body": "Hello <script>not html</script>"},
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(response.status_code, 204)
        message = ChatMessage.objects.get(channel=self.channel)
        pusher_client.trigger.assert_called_once_with(
            f"private-chat-{self.channel.pk}",
            "message-created",
            {"message_id": message.pk, "channel_id": self.channel.pk},
        )

    def test_authorized_fragment_escapes_body_and_rejects_outsider(self):
        message = ChatMessage.objects.create(
            user=self.member,
            channel=self.channel,
            body="<script>alert(1)</script>",
        )
        url = reverse(
            "chat:message-fragment", args=[self.channel.pk, message.pk]
        )
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.member)
        response = self.client.get(url)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_fragment_is_bound_to_the_requested_channel(self):
        other_channel = ChatChannel.objects.create(
            title="other",
            topic="Other topic",
            category=self.category,
        )
        other_message = ChatMessage.objects.create(
            user=self.member,
            channel=other_channel,
            body="Must not cross channel context",
        )
        forged_url = reverse(
            "chat:message-fragment",
            args=[self.channel.pk, other_message.pk],
        )
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(forged_url).status_code, 404)

    def test_message_deletion_is_post_only_and_authorized(self):
        message = ChatMessage.objects.create(
            user=self.member, channel=self.channel, body="Delete me"
        )
        url = reverse("chat:msg-delete", args=[message.pk])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(ChatMessage.objects.filter(pk=message.pk).exists())

    def test_identical_messages_are_not_suppressed(self):
        self.client.force_login(self.member)
        url = reverse("chat:chat-channel", args=[self.channel.pk])
        with patch("Chat.views.get_pusher_client"):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {"body": "same"})
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(url, {"body": "same"})
        self.assertEqual(ChatMessage.objects.filter(channel=self.channel).count(), 2)


class DemoChatTests(TestCase):
    def test_demo_can_chat_but_cannot_create_channels(self):
        group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo")
        demo.groups.add(group)
        dome = make_dome(demo, title="Demo Dome", privacy=0)
        category = Category.objects.create(title="General", Dome=dome)
        channel = ChatChannel.objects.create(
            title="chat", topic="Topic", category=category
        )
        self.client.force_login(demo)
        self.assertEqual(
            self.client.get(reverse("chat:chat-channel", args=[channel.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                reverse("chat:chatchannel-create", args=[category.pk]),
                {"title": "new", "topic": "No"},
            ).status_code,
            403,
        )
