from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
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
    def setUp(self):
        self.owner = User.objects.create_user("media-owner", password="x")
        Profile.objects.filter(user=self.owner).update(picture="")
        self.dome = Dome.objects.create(
            user=self.owner,
            title="Media",
            description="Migration coverage",
            privacy=1,
            icon=None,
            banner=None,
        )
        self.post = Post.objects.create(
            user=self.owner,
            question_text="Media migration",
            content="<p>Body</p>",
            picture=None,
        )

    def set_references(self, *, profile="", icon=None, banner=None, post=None):
        Profile.objects.filter(user=self.owner).update(picture=profile)
        Dome.objects.filter(pk=self.dome.pk).update(icon=icon, banner=banner)
        Post.objects.filter(pk=self.post.pk).update(picture=post)

    def run_migration(self, flag, *, media_root, private_root, source_root=None):
        stdout, stderr = StringIO(), StringIO()
        arguments = [flag]
        if source_root is not None:
            arguments.extend(["--source-root", str(source_root)])
        with self.settings(
            MEDIA_ROOT=media_root,
            PRIVATE_MEDIA_ROOT=private_root,
        ):
            call_command(
                "migrate_private_media",
                *arguments,
                stdout=stdout,
                stderr=stderr,
            )
        return stdout.getvalue(), stderr.getvalue()

    def test_external_source_dry_run_apply_bytes_retention_and_rerun(self):
        name = "shared/existing.jpg"
        payload = b"legacy image bytes\x00\xff"
        self.set_references(profile=name, icon=name, post=name)

        with (
            TemporaryDirectory() as configured_media_root,
            TemporaryDirectory() as source_root,
            TemporaryDirectory() as private_root,
        ):
            legacy = FileSystemStorage(location=source_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(name, ContentFile(payload))

            dry_stdout, dry_stderr = self.run_migration(
                "--dry-run",
                media_root=configured_media_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("would copy 1; already private 0; missing 0", dry_stdout)
            self.assertEqual(dry_stderr, "")
            self.assertFalse(private.exists(name))

            apply_stdout, apply_stderr = self.run_migration(
                "--apply",
                media_root=configured_media_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("copied 1; already private 0; missing 0", apply_stdout)
            self.assertEqual(apply_stderr, "")
            with private.open(name, "rb") as copied:
                self.assertEqual(copied.read(), payload)
            with legacy.open(name, "rb") as original:
                self.assertEqual(original.read(), payload)

            rerun_stdout, rerun_stderr = self.run_migration(
                "--apply",
                media_root=configured_media_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("copied 0; already private 1; missing 0", rerun_stdout)
            self.assertEqual(rerun_stderr, "")

    def test_mismatched_destination_is_reported_replaced_and_idempotent(self):
        name = "shared/mismatched.jpg"
        source_payload = b"authoritative legacy bytes"
        stale_payload = b"stale private bytes"
        self.set_references(profile=name)

        with TemporaryDirectory() as source_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=source_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(name, ContentFile(source_payload))
            private.save(name, ContentFile(stale_payload))

            dry_stdout, _ = self.run_migration(
                "--dry-run",
                media_root=source_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("would replace 1", dry_stdout)
            with private.open(name, "rb") as destination:
                self.assertEqual(destination.read(), stale_payload)

            apply_stdout, _ = self.run_migration(
                "--apply",
                media_root=source_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("replaced 1", apply_stdout)
            with private.open(name, "rb") as destination:
                self.assertEqual(destination.read(), source_payload)
            with legacy.open(name, "rb") as source:
                self.assertEqual(source.read(), source_payload)

            rerun_stdout, _ = self.run_migration(
                "--apply",
                media_root=source_root,
                private_root=private_root,
                source_root=source_root,
            )
            self.assertIn("copied 0; already private 1; missing 0", rerun_stdout)
            self.assertIn("replaced 0", rerun_stdout)

    def test_interrupted_replacement_write_keeps_old_destination_and_cleans_temp(self):
        name = "shared/write-failure.jpg"
        source_payload = b"new source"
        stale_payload = b"old destination"
        self.set_references(profile=name)

        with TemporaryDirectory() as source_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=source_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(name, ContentFile(source_payload))
            private.save(name, ContentFile(stale_payload))

            def interrupted_copy(source, destination):
                destination.write(source.read(3))
                raise OSError("simulated interrupted write")

            with patch(
                "users.management.commands.migrate_private_media._copy_chunks",
                side_effect=interrupted_copy,
            ), self.assertRaisesMessage(CommandError, "atomically replace"):
                self.run_migration(
                    "--apply",
                    media_root=source_root,
                    private_root=private_root,
                    source_root=source_root,
                )

            with private.open(name, "rb") as destination:
                self.assertEqual(destination.read(), stale_payload)
            destination_parent = Path(private.path(name)).parent
            self.assertEqual(list(destination_parent.glob(".write-failure.jpg.*.tmp")), [])

    @patch(
        "users.management.commands.migrate_private_media.os.replace",
        side_effect=OSError("simulated interrupted replace"),
    )
    def test_interrupted_atomic_replace_keeps_old_destination_and_cleans_temp(
        self, _replace
    ):
        name = "shared/replace-failure.jpg"
        source_payload = b"new source"
        stale_payload = b"old destination"
        self.set_references(profile=name)

        with TemporaryDirectory() as source_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=source_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(name, ContentFile(source_payload))
            private.save(name, ContentFile(stale_payload))

            with self.assertRaisesMessage(CommandError, "atomically replace"):
                self.run_migration(
                    "--apply",
                    media_root=source_root,
                    private_root=private_root,
                    source_root=source_root,
                )

            with private.open(name, "rb") as destination:
                self.assertEqual(destination.read(), stale_payload)
            destination_parent = Path(private.path(name)).parent
            self.assertEqual(
                list(destination_parent.glob(".replace-failure.jpg.*.tmp")), []
            )

    def test_source_root_defaults_to_media_root(self):
        name = "posts/from-default.jpg"
        payload = b"default source bytes"
        self.set_references(post=name)

        with TemporaryDirectory() as media_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=media_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(name, ContentFile(payload))

            stdout, stderr = self.run_migration(
                "--apply",
                media_root=media_root,
                private_root=private_root,
            )

            self.assertIn("copied 1; already private 0; missing 0", stdout)
            self.assertEqual(stderr, "")
            with private.open(name, "rb") as copied:
                self.assertEqual(copied.read(), payload)

    def test_source_root_must_be_absolute(self):
        with TemporaryDirectory() as media_root, TemporaryDirectory() as private_root:
            with self.assertRaisesMessage(CommandError, "must be an absolute path"):
                self.run_migration(
                    "--dry-run",
                    media_root=media_root,
                    private_root=private_root,
                    source_root="relative-media",
                )

    def test_source_root_must_exist(self):
        with TemporaryDirectory() as parent, TemporaryDirectory() as private_root:
            missing_root = Path(parent) / "missing"
            with self.assertRaisesMessage(CommandError, "does not exist"):
                self.run_migration(
                    "--dry-run",
                    media_root=parent,
                    private_root=private_root,
                    source_root=missing_root,
                )

    def test_source_root_must_be_a_directory(self):
        with TemporaryDirectory() as parent, TemporaryDirectory() as private_root:
            source_file = Path(parent) / "legacy-media.txt"
            source_file.write_bytes(b"not a directory")
            with self.assertRaisesMessage(CommandError, "is not a directory"):
                self.run_migration(
                    "--dry-run",
                    media_root=parent,
                    private_root=private_root,
                    source_root=source_file,
                )

    def test_source_root_must_not_equal_private_root(self):
        with TemporaryDirectory() as shared_root:
            with self.assertRaisesMessage(CommandError, "must be different"):
                self.run_migration(
                    "--dry-run",
                    media_root=shared_root,
                    private_root=shared_root,
                    source_root=shared_root,
                )

    def test_missing_reference_aborts_before_any_copy(self):
        present_name = "posts/present.jpg"
        replacement_name = "profile_pics/stale.jpg"
        missing_name = "domes/missing.jpg"
        payload = b"must not be copied"
        replacement_payload = b"authoritative replacement"
        stale_payload = b"must remain on abort"
        self.set_references(
            profile=present_name,
            icon=missing_name,
            banner=replacement_name,
        )

        with TemporaryDirectory() as source_root, TemporaryDirectory() as private_root:
            legacy = FileSystemStorage(location=source_root, base_url=None)
            private = FileSystemStorage(location=private_root, base_url=None)
            legacy.save(present_name, ContentFile(payload))
            legacy.save(replacement_name, ContentFile(replacement_payload))
            private.save(replacement_name, ContentFile(stale_payload))
            stderr = StringIO()

            with self.settings(
                MEDIA_ROOT=source_root,
                PRIVATE_MEDIA_ROOT=private_root,
            ), self.assertRaisesMessage(CommandError, "aborted before copying"):
                call_command(
                    "migrate_private_media",
                    "--apply",
                    "--source-root",
                    source_root,
                    stdout=StringIO(),
                    stderr=stderr,
                )

            self.assertIn(missing_name, stderr.getvalue())
            self.assertFalse(private.exists(present_name))
            self.assertFalse(private.exists(missing_name))
            with private.open(replacement_name, "rb") as destination:
                self.assertEqual(destination.read(), stale_payload)
            with legacy.open(present_name, "rb") as original:
                self.assertEqual(original.read(), payload)


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
        self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        self.assertLessEqual(int(response.headers["Retry-After"]), 300)

    def test_login_rotating_accounts_cannot_bypass_ip_limit(self):
        url = reverse("users:login")
        for attempt in range(8):
            response = self.client.post(
                url,
                {"username": f"rotated-{attempt}", "password": "wrong"},
                REMOTE_ADDR="203.0.113.40",
            )
            self.assertNotEqual(response.status_code, 429)

        response = self.client.post(
            url,
            {"username": "rotated-final", "password": "wrong"},
            REMOTE_ADDR="203.0.113.40",
        )
        self.assertEqual(response.status_code, 429)

    def test_login_repeated_normalized_account_is_limited_across_ips(self):
        url = reverse("users:login")
        variants = ("RepeatedAccount", " repeatedaccount ")
        for attempt in range(8):
            response = self.client.post(
                url,
                {"username": variants[attempt % 2], "password": "wrong"},
                REMOTE_ADDR=f"203.0.113.{50 + attempt}",
            )
            self.assertNotEqual(response.status_code, 429)

        response = self.client.post(
            url,
            {"username": "REPEATEDACCOUNT", "password": "wrong"},
            REMOTE_ADDR="203.0.113.99",
        )
        self.assertEqual(response.status_code, 429)

    def test_login_gets_are_never_rate_limited(self):
        url = reverse("users:login")
        for _ in range(20):
            self.assertEqual(
                self.client.get(url, REMOTE_ADDR="203.0.113.4").status_code,
                200,
            )

    def test_registration_is_rate_limited_after_five_posts(self):
        url = reverse("users:register")
        for attempt in range(5):
            self.assertEqual(
                self.client.post(
                    url,
                    {"username": f"rotated-{attempt}"},
                    REMOTE_ADDR="203.0.113.5",
                ).status_code,
                200,
            )
        response = self.client.post(
            url,
            {"username": "rotated-final"},
            REMOTE_ADDR="203.0.113.5",
        )
        self.assertEqual(response.status_code, 429)

    def test_registration_gets_are_never_rate_limited(self):
        url = reverse("users:register")
        for _ in range(10):
            self.assertEqual(
                self.client.get(url, REMOTE_ADDR="203.0.113.5").status_code,
                200,
            )

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
