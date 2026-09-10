from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from Chat.models import ChatChannel
from Domes.models import Category, Dome, validate_dome_image
from posts.models import Post, validate_image

from .models import Profile, validate_profile_image


class _SizedUpload(BytesIO):
    def __init__(self, size):
        super().__init__(b"not-decoded-because-image-open-is-mocked")
        self.size = size
        self.content_type = "image/png"
        self.name = "boundary.png"


class _DecodedImage:
    format = "PNG"

    def __init__(self, size):
        self.size = size

    def verify(self):
        return None


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


class UploadValidatorBoundaryTests(TestCase):
    def test_size_and_pixel_boundaries_for_all_private_image_types(self):
        cases = (
            (validate_image, "posts.models.Image.open", 4 * 1024 * 1024, (5000, 4000), (5000, 4001)),
            (validate_profile_image, "users.models.Image.open", 4 * 1024 * 1024, (4000, 4000), (4000, 4001)),
            (validate_dome_image, "Domes.models.Image.open", 5 * 1024 * 1024, (6000, 4000), (6000, 4001)),
        )
        for validator, image_open, max_bytes, exact_pixels, over_pixels in cases:
            with self.subTest(validator=validator.__name__, boundary="exact"):
                with patch(image_open, return_value=_DecodedImage(exact_pixels)):
                    validator(_SizedUpload(max_bytes))
            with self.subTest(validator=validator.__name__, boundary="bytes"):
                with self.assertRaises(ValidationError):
                    validator(_SizedUpload(max_bytes + 1))
            with self.subTest(validator=validator.__name__, boundary="pixels"):
                with patch(image_open, return_value=_DecodedImage(over_pixels)):
                    with self.assertRaises(ValidationError):
                        validator(_SizedUpload(1))


class PrivateMediaMigrationTests(TestCase):
    def test_dry_run_apply_rerun_and_missing_file_are_safe(self):
        owner = User.objects.create_user("media-owner", password="x")
        existing_name = "shared/existing.jpg"
        missing_name = "posts/missing.jpg"
        Profile.objects.filter(user=owner).update(picture=existing_name)
        Dome.objects.create(
            user=owner,
            title="Media",
            description="Migration coverage",
            privacy=1,
            icon=existing_name,
            banner=None,
        )
        Post.objects.create(
            user=owner,
            question_text="Missing media",
            content="<p>Body</p>",
            picture=missing_name,
        )

        with TemporaryDirectory() as legacy_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=legacy_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(existing_name, ContentFile(b"legacy image bytes"))

            def run_migration(flag):
                stdout, stderr = StringIO(), StringIO()
                with self.settings(MEDIA_ROOT=legacy_root), patch(
                    "users.management.commands.migrate_private_media.private_media_storage",
                    private,
                ):
                    call_command("migrate_private_media", flag, stdout=stdout, stderr=stderr)
                return stdout.getvalue(), stderr.getvalue()

            dry_stdout, dry_stderr = run_migration("--dry-run")
            self.assertIn("would copy 1; already private 0; missing 1", dry_stdout)
            self.assertIn(missing_name, dry_stderr)
            self.assertFalse(private.exists(existing_name))

            apply_stdout, apply_stderr = run_migration("--apply")
            self.assertIn("copied 1; already private 0; missing 1", apply_stdout)
            self.assertIn(missing_name, apply_stderr)
            self.assertTrue(private.exists(existing_name))
            self.assertTrue(legacy.exists(existing_name))

            rerun_stdout, _ = run_migration("--apply")
            self.assertIn("copied 0; already private 1; missing 1", rerun_stdout)


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

    def test_demo_login_fails_closed_when_user_is_missing(self):
        response = self.client.post(reverse("users:demo_login"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_demo_login_fails_closed_when_dome_is_missing(self):
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("guest-sandbox")
        demo.set_unusable_password()
        demo.save(update_fields=["password"])
        demo.groups.add(demo_group)
        response = self.client.post(reverse("users:demo_login"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_demo_login_is_rate_limited_after_twenty_attempts(self):
        url = reverse("users:demo_login")
        for _ in range(20):
            self.assertEqual(self.client.post(url).status_code, 503)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

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
    def setUp(self):
        cache.clear()

    def test_login_attempts_are_rate_limited(self):
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

    def test_registration_is_rate_limited_after_five_posts(self):
        url = reverse("users:register")
        for _ in range(5):
            self.assertEqual(self.client.post(url, {}).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 429)

    def test_password_reset_is_rate_limited_after_five_posts(self):
        url = reverse("password_reset")
        for _ in range(5):
            self.assertEqual(
                self.client.post(url, {"email": "missing@example.com"}).status_code,
                302,
            )
        self.assertEqual(
            self.client.post(url, {"email": "missing@example.com"}).status_code,
            429,
        )

    def test_profile_update_is_rate_limited_after_ten_posts(self):
        user = User.objects.create_user("profile-rate", password="x")
        self.client.force_login(user)
        url = reverse("users:profile")
        for _ in range(10):
            self.assertEqual(self.client.post(url, {}).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 429)


class UserSearchTests(TestCase):
    def test_search_paginates_real_users_and_excludes_demo_accounts(self):
        viewer = User.objects.create_user("viewer", password="x")
        for index in range(11):
            User.objects.create_user(f"match-{index:02d}", password="x")
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("match-demo")
        demo.groups.add(demo_group)
        self.client.force_login(viewer)

        first = self.client.get(reverse("users:user_search"), {"q": "match-"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.context["users"].paginator.count, 11)
        self.assertEqual(len(first.context["users"]), 10)
        self.assertNotIn(demo, first.context["users"].object_list)

        second = self.client.get(
            reverse("users:user_search"), {"q": "match-", "page": 2}
        )
        self.assertEqual(len(second.context["users"]), 1)

    def test_blank_search_does_not_enumerate_users(self):
        viewer = User.objects.create_user("blank-viewer", password="x")
        User.objects.create_user("not-listed", password="x")
        self.client.force_login(viewer)
        response = self.client.get(reverse("users:user_search"), {"q": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("users", response.context)
