from unittest.mock import Mock, patch

from django.contrib.auth.models import Group, User
from django.core.cache import cache
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
        cache.clear()
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
        self.assertEqual(response.status_code, 201)
        self.assertContains(
            response,
            "Hello &lt;script&gt;not html&lt;/script&gt;",
            status_code=201,
        )
        message = ChatMessage.objects.get(channel=self.channel)
        pusher_client.trigger.assert_called_once_with(
            f"private-chat-{self.channel.pk}",
            "message-created",
            {"message_id": message.pk, "channel_id": self.channel.pk},
        )

    @patch("Chat.views.get_pusher_client")
    def test_htmx_send_returns_saved_fragment_when_realtime_publish_fails(
        self, get_client
    ):
        get_client.return_value.trigger.side_effect = RuntimeError("realtime down")
        self.client.force_login(self.member)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chat:chat-channel", args=[self.channel.pk]),
                {"body": "Saved despite outage"},
                HTTP_HX_REQUEST="true",
            )
        message = ChatMessage.objects.get(channel=self.channel)
        self.assertEqual(response.status_code, 201)
        self.assertContains(response, "Saved despite outage", status_code=201)
        self.assertContains(
            response,
            f'id="message-{message.pk}"',
            status_code=201,
        )

    def test_first_chat_page_contains_newest_fifty_and_links_to_older_messages(self):
        for index in range(55):
            ChatMessage.objects.create(
                user=self.member,
                channel=self.channel,
                body=f"message-{index:02d}",
            )
        self.client.force_login(self.member)
        url = reverse("chat:chat-channel", args=[self.channel.pk])
        response = self.client.get(url)
        self.assertContains(response, "message-54")
        self.assertContains(response, "message-05")
        self.assertNotContains(response, "message-04")
        self.assertContains(response, "Load earlier messages")
        self.assertLess(
            response.content.index(b"message-05"),
            response.content.index(b"message-54"),
        )

        older = self.client.get(url, {"page": 2})
        self.assertContains(older, "message-00")
        self.assertContains(older, "message-04")
        self.assertNotContains(older, "message-05")
        self.assertNotContains(older, "Load earlier messages")

    def test_channel_route_supports_native_and_htmx_navigation(self):
        self.client.force_login(self.member)
        url = reverse("chat:chat-channel", args=[self.channel.pk])

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'class="dome-shell"')
        self.assertContains(page, f'href="{url}"')
        self.assertContains(page, 'aria-current="page"')
        self.assertEqual(page.context["active_section"], "chat")
        self.assertEqual(page.context["active_channel_id"], self.channel.pk)
        self.assertIn("HX-Request", page.headers.get("Vary", ""))

        fragment = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(fragment.status_code, 200)
        self.assertContains(fragment, 'class="chat-panel"')
        self.assertNotContains(fragment, 'class="dome-shell"')
        self.assertNotContains(fragment, "hx-on::")
        self.assertNotContains(fragment, "new Pusher")

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

    def test_blank_non_htmx_message_returns_400_without_creating_a_row(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("chat:chat-channel", args=[self.channel.pk]),
            {"body": "   "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatMessage.objects.filter(channel=self.channel).exists())

    @patch("Chat.views.get_pusher_client")
    def test_normal_message_send_trims_persists_and_redirects(self, get_client):
        self.client.force_login(self.member)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chat:chat-channel", args=[self.channel.pk]),
                {"body": "  Normal message  "},
            )
        message = ChatMessage.objects.get(channel=self.channel)
        self.assertEqual(message.body, "Normal message")
        self.assertRedirects(
            response,
            reverse("chat:chat-channel", args=[self.channel.pk]),
            fetch_redirect_response=False,
        )
        get_client.return_value.trigger.assert_called_once()

    def test_duplicate_channel_title_is_rejected_case_insensitively(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("chat:chatchannel-create", args=[self.category.pk]),
            {"title": " CHAT ", "topic": "Duplicate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatChannel.objects.filter(category=self.category).count(), 1)

    def test_message_creation_is_rate_limited_after_forty_posts(self):
        self.client.force_login(self.member)
        url = reverse("chat:chat-channel", args=[self.channel.pk])
        for index in range(40):
            self.assertEqual(
                self.client.post(url, {"body": f"message-{index}"}).status_code,
                302,
            )
        response = self.client.post(url, {"body": "one-too-many"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(ChatMessage.objects.filter(channel=self.channel).count(), 40)


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
