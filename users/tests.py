from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from Chat.models import ChatChannel
from Domes.models import Category, Dome
from posts.models import Post

from .models import Profile


class ProfileTests(TestCase):
    def test_profile_is_created_once_by_user_signal(self):
        user = User.objects.create_user("testuser", password="x")
        profile = Profile.objects.get(user=user)
        self.assertEqual(str(profile), "testuser Profile")
        self.assertEqual(profile.picture.name, "profile_pics/default.jpg")


class ProtectedImageResponseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("image-owner", password="x")
        self.dome = Dome.objects.create(
            user=self.user,
            title="Images",
            description="Protected image tests",
            privacy=1,
            icon=None,
            banner=None,
        )
        self.post = Post.objects.create(
            user=self.user,
            question_text="Image post",
            content="<p>Body</p>",
        )
        image = BytesIO()
        Image.new("RGB", (2, 2), "white").save(image, format="JPEG")
        self.jpeg_bytes = image.getvalue()

        Dome.objects.filter(pk=self.dome.pk).update(icon="domes/image.html")
        Post.objects.filter(pk=self.post.pk).update(picture="posts/image.html")
        Profile.objects.filter(user=self.user).update(
            picture="profile_pics/image.html"
        )
        self.dome.refresh_from_db()
        self.post.refresh_from_db()

    @patch("Domes.storage.open_private_or_legacy")
    def test_all_protected_routes_detect_jpeg_bytes_despite_html_suffix(self, opener):
        opener.side_effect = lambda field_file: BytesIO(self.jpeg_bytes)
        self.client.force_login(self.user)

        for url in (
            reverse("domes:dome-media", args=[self.dome.pk, "icon"]),
            reverse("posts:post-picture", args=[self.post.pk]),
            reverse("users:profile_picture", args=[self.user.username]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["Content-Type"], "image/jpeg")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertTrue(
                response.headers["Content-Disposition"].endswith('.jpg"')
            )
            response.close()


@override_settings(
    DEMO_ACCOUNT_ENABLED=True,
    DEMO_USERNAME="guest-sandbox",
    DEMO_DOME_TITLE="Guest Dome",
)
class DemoSandboxTests(TestCase):
    def setUp(self):
        cache.clear()

    def reset(self):
        call_command("reset_demo_sandbox", stdout=StringIO())
        return User.objects.get(username="guest-sandbox")

    def test_reset_is_idempotent_and_builds_one_owned_private_sandbox(self):
        first_user = self.reset()
        first_pk = first_user.pk
        self.assertFalse(first_user.has_usable_password())
        self.assertTrue(first_user.groups.filter(name="Demo").exists())
        first_dome = Dome.objects.get(user=first_user)
        self.assertEqual(first_dome.privacy, 0)
        self.assertEqual(Category.objects.filter(Dome=first_dome).count(), 1)
        self.assertEqual(
            ChatChannel.objects.filter(category__Dome=first_dome).count(), 1
        )
        self.assertEqual(Post.objects.filter(dome=first_dome).count(), 1)

        Post.objects.create(
            user=first_user,
            dome=first_dome,
            question_text="Temporary",
            content="<p>remove me</p>",
        )
        second_user = self.reset()
        self.assertEqual(second_user.pk, first_pk)
        self.assertEqual(Dome.objects.filter(user=second_user).count(), 1)
        self.assertEqual(Post.objects.filter(user=second_user).count(), 1)

    def test_demo_login_is_post_only_and_sets_short_nonindexed_session(self):
        demo = self.reset()
        url = reverse("users:demo_login")
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(int(self.client.session["_auth_user_id"]), demo.pk)
        self.assertLessEqual(self.client.session.get_expiry_age(), 30 * 60)

    def test_demo_login_rejects_usable_password_account(self):
        demo = self.reset()
        demo.set_password("must-not-be-shared")
        demo.save(update_fields=["password"])
        response = self.client.post(reverse("users:demo_login"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_demo_profile_and_search_are_forbidden(self):
        demo = self.reset()
        self.client.force_login(demo)
        self.assertEqual(self.client.get(reverse("users:profile")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("users:user_search"), {"q": "user"}).status_code,
            403,
        )


class DisabledDemoTests(TestCase):
    @override_settings(DEMO_ACCOUNT_ENABLED=False, DEMO_USERNAME="disabled-demo")
    def test_disabled_demo_endpoint_refuses_login(self):
        group = Group.objects.create(name="Demo")
        user = User.objects.create_user("disabled-demo")
        user.set_unusable_password()
        user.save(update_fields=["password"])
        user.groups.add(group)
        Dome.objects.create(
            user=user,
            title="Disabled",
            description="Disabled",
            privacy=0,
            icon=None,
            banner=None,
        )
        response = self.client.post(reverse("users:demo_login"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("_auth_user_id", self.client.session)


class AuthenticationRateLimitTests(TestCase):
    def test_login_attempts_are_rate_limited(self):
        cache.clear()
        url = reverse("users:login")
        for _ in range(8):
            self.assertNotEqual(
                self.client.post(
                    url,
                    {"username": "missing", "password": "wrong"},
                    REMOTE_ADDR="203.0.113.4",
                ).status_code,
                429,
            )
        response = self.client.post(
            url,
            {"username": "missing", "password": "wrong"},
            REMOTE_ADDR="203.0.113.4",
        )
        self.assertEqual(response.status_code, 429)
