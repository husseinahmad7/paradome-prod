from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO, StringIO
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from Domes.models import Dome
from notify.models import Notification

from .access import accessible_posts, can_access_post
from .models import Comment, Follow, Like, Post, Stream, validate_image


def make_dome(owner, *, title="Private Dome", privacy=0):
    return Dome.objects.create(
        title=title,
        description="Security test",
        user=owner,
        privacy=privacy,
        icon=None,
        banner=None,
    )


class PostContainmentTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x")
        self.member = User.objects.create_user("member", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        self.dome = make_dome(self.owner)
        self.dome.members.add(self.member)
        self.post = Post.objects.create(
            user=self.owner,
            dome=self.dome,
            question_text="Private post",
            content="<p>secret</p>",
        )

    def test_nested_post_uses_parent_dome_visibility(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("posts:post-detail", args=[self.post.pk]))
        self.assertEqual(response.status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(reverse("posts:post-detail", args=[self.post.pk])).status_code,
            200,
        )

    def test_like_is_post_only_and_counter_is_authoritative(self):
        self.client.force_login(self.member)
        url = reverse("posts:like", args=[self.post.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.likes, 1)
        self.assertEqual(Like.objects.filter(post=self.post).count(), 1)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.likes, 0)

    def test_like_requires_a_valid_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        like_url = reverse("posts:like", args=[self.post.pk])

        self.assertEqual(csrf_client.post(like_url).status_code, 403)

        detail_response = csrf_client.get(
            reverse("posts:post-detail", args=[self.post.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        csrf_token = csrf_client.cookies["csrftoken"].value
        self.assertEqual(
            csrf_client.post(
                like_url,
                HTTP_X_CSRFTOKEN=csrf_token,
            ).status_code,
            200,
        )

    def test_like_constraint_blocks_duplicates(self):
        Like.objects.create(user=self.member, post=self.post)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Like.objects.create(user=self.member, post=self.post)

    def test_comment_delete_checks_post_and_authority(self):
        comment = Comment.objects.create(
            post=self.post, user=self.member, comment="<p>hello</p>"
        )
        url = reverse("posts:comment-delete", args=[comment.pk])
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    def test_protected_post_media_denies_outsider_before_open(self):
        Post.objects.filter(pk=self.post.pk).update(picture="posts/private.png")
        self.client.force_login(self.outsider)
        self.assertEqual(
            self.client.get(reverse("posts:post-picture", args=[self.post.pk])).status_code,
            404,
        )

    def test_user_and_stream_like_controls_load_htmx_and_csrf_bootstrap(self):
        self.client.force_login(self.member)
        like_url = reverse("posts:like", args=[self.post.pk])
        Stream.objects.create(
            following=self.owner,
            user=self.member,
            post=self.post,
            date=self.post.posted_date,
        )

        for page_url in (
            reverse("posts:user-posts", args=[self.owner.username]),
            reverse("posts:stream"),
        ):
            response = self.client.get(page_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'src="/static/js/htmx.min.js"')
            self.assertContains(response, "htmx:configRequest")
            self.assertContains(response, f'hx-post="{like_url}"')


class RichTextSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("writer", password="x")

    def test_save_time_sanitizer_removes_active_content(self):
        post = Post.objects.create(
            user=self.user,
            question_text="XSS",
            content='<p onclick="alert(1)">ok</p><script>alert(2)</script>',
        )
        self.assertEqual(post.content, "<p>ok</p>")
        comment = Comment.objects.create(
            user=self.user,
            post=post,
            comment='<a href="javascript:alert(1)">link</a>',
        )
        self.assertNotIn("javascript:", comment.comment)

    def test_image_validator_rejects_spoofed_declared_mime(self):
        image_bytes = BytesIO()
        Image.new("RGB", (2, 2), "white").save(image_bytes, format="PNG")
        upload = SimpleUploadedFile(
            "spoofed.jpg", image_bytes.getvalue(), content_type="image/jpeg"
        )
        with self.assertRaises(ValidationError):
            validate_image(upload)

    def test_render_time_sanitizer_protects_legacy_rows(self):
        post = Post.objects.create(
            user=self.user,
            question_text="Legacy",
            content="<p>safe</p>",
        )
        Post.objects.filter(pk=post.pk).update(content="<script>alert(1)</script><p>safe</p>")
        response = self.client.get(reverse("posts:post-detail", args=[post.pk]))
        self.assertNotContains(response, "<script>alert(1)</script>", html=False)
        self.assertContains(response, "<p>safe</p>", html=True)

    def test_sanitize_command_reports_then_applies(self):
        post = Post.objects.create(user=self.user, question_text="Legacy", content="<p>ok</p>")
        Post.objects.filter(pk=post.pk).update(content="<script>x</script><p>ok</p>")
        output = StringIO()
        call_command("sanitize_rich_text", "--dry-run", stdout=output)
        self.assertIn("posts 1/1 changed", output.getvalue())
        call_command("sanitize_rich_text", "--apply", stdout=StringIO())
        post.refresh_from_db()
        self.assertEqual(post.content, "<p>ok</p>")


class DemoAndSocialPolicyTests(TestCase):
    def setUp(self):
        group = Group.objects.create(name="Demo")
        self.demo = User.objects.create_user("demo")
        self.demo.groups.add(group)
        self.real = User.objects.create_user("real", password="x")
        self.demo_dome = make_dome(self.demo, title="Demo Dome")
        self.demo_post = Post.objects.create(
            user=self.demo,
            dome=self.demo_dome,
            question_text="Demo post",
            content="<p>demo</p>",
        )

    def test_demo_can_only_access_owned_dome_posts(self):
        real_post = Post.objects.create(
            user=self.real, question_text="Real", content="<p>real</p>"
        )
        legacy_demo_global = Post.objects.create(
            user=self.demo, question_text="Legacy", content="<p>legacy</p>"
        )
        self.assertFalse(can_access_post(self.demo, real_post))
        self.assertFalse(can_access_post(self.real, legacy_demo_global))
        self.assertEqual(list(accessible_posts(self.demo)), [self.demo_post])

    def test_demo_can_create_text_post_only_in_owned_dome(self):
        self.client.force_login(self.demo)
        response = self.client.post(
            reverse("posts:domepost-create", args=[self.demo_dome.pk]),
            {"question_text": "A safe demo post", "content": "<p>Hello</p>"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Post.objects.filter(
                dome=self.demo_dome, question_text="A safe demo post"
            ).exists()
        )
        self.assertEqual(
            self.client.post(
                reverse("posts:post-create"),
                {"question_text": "Global", "content": "<p>No</p>"},
            ).status_code,
            403,
        )

    def test_demo_post_form_hides_and_rejects_uploads(self):
        self.client.force_login(self.demo)
        url = reverse("posts:domepost-create", args=[self.demo_dome.pk])
        response = self.client.get(url)
        self.assertNotContains(response, 'name="picture"')
        self.assertNotContains(response, "Create a tag")
        self.assertContains(response, "Guest mode is text only")

        upload = SimpleUploadedFile(
            "demo.txt",
            b"not allowed",
            content_type="text/plain",
        )
        response = self.client.post(
            url,
            {
                "question_text": "Upload attempt",
                "content": "<p>No file should be stored.</p>",
                "picture": upload,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demo accounts cannot upload files.")
        self.assertFalse(
            Post.objects.filter(
                dome=self.demo_dome,
                question_text="Upload attempt",
            ).exists()
        )

    def test_dome_posts_route_supports_native_and_htmx_navigation(self):
        self.client.force_login(self.demo)
        url = reverse("posts:htmxdomeposts", args=[self.demo_dome.pk])

        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'class="dome-shell"')
        self.assertContains(page, "Dome posts")
        self.assertContains(page, "Demo post")
        self.assertEqual(page.context["active_section"], "posts")
        self.assertIn("HX-Request", page.headers.get("Vary", ""))

        fragment = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(fragment.status_code, 200)
        self.assertContains(fragment, "Dome posts")
        self.assertContains(fragment, "Demo post")
        self.assertNotContains(fragment, 'class="dome-shell"')

    def test_reply_dialog_fragment_has_no_csp_blocked_inline_script(self):
        comment = Comment.objects.create(
            user=self.demo,
            post=self.demo_post,
            comment="Parent reply",
        )
        self.client.force_login(self.demo)
        response = self.client.get(
            reverse("posts:comment-replies", args=[comment.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="dialog"')
        self.assertNotContains(response, "<script")

    def test_demo_cannot_edit_or_moderate_posts(self):
        self.client.force_login(self.demo)
        self.assertEqual(
            self.client.get(
                reverse("posts:post-update", args=[self.demo_post.pk])
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("posts:post-delete", args=[self.demo_post.pk])
            ).status_code,
            403,
        )

    def test_demo_cannot_follow_and_follow_is_post_only(self):
        url = reverse("posts:follow", args=[self.real.username, 1])
        self.client.force_login(self.demo)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.real)
        other = User.objects.create_user("other", password="x")
        real_url = reverse("posts:follow", args=[other.username, 1])
        self.assertEqual(self.client.get(real_url).status_code, 405)
        self.assertEqual(self.client.post(real_url).status_code, 302)
        self.assertTrue(Follow.objects.filter(follower=self.real, following=other).exists())

    def test_demo_actions_never_notify_real_users(self):
        real_post = Post.objects.create(
            user=self.real, question_text="Real", content="<p>real</p>"
        )
        Like.objects.create(user=self.demo, post=real_post)
        self.assertFalse(Notification.objects.filter(sender=self.demo).exists())

    def test_tag_creation_is_rate_limited(self):
        cache.clear()
        self.client.force_login(self.real)
        url = reverse("posts:tag-create")
        for index in range(15):
            self.assertEqual(
                self.client.post(url, {"title": f"tag-{index}"}).status_code,
                302,
            )
        self.assertEqual(
            self.client.post(url, {"title": "one-too-many"}).status_code,
            429,
        )


class FollowAndStreamTests(TestCase):
    def setUp(self):
        cache.clear()
        self.actor = User.objects.create_user("stream-reader", password="x")
        self.author = User.objects.create_user("stream-author", password="x")
        self.client.force_login(self.actor)

    def test_follow_rejects_self_invalid_action_and_missing_target(self):
        self.assertEqual(
            self.client.post(
                reverse("posts:follow", args=[self.actor.username, 1])
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                reverse("posts:follow", args=[self.author.username, 7])
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                reverse("posts:follow", args=["missing-user", 1])
            ).status_code,
            404,
        )
        self.assertFalse(Follow.objects.exists())

    def test_unfollow_removes_follow_stream_and_notification(self):
        post = Post.objects.create(
            user=self.author,
            question_text="Existing post",
            content="<p>Body</p>",
        )
        follow = Follow.objects.create(follower=self.actor, following=self.author)
        Stream.objects.create(
            user=self.actor,
            following=self.author,
            post=post,
            date=post.posted_date,
        )
        source_key = f"follow:{follow.pk}"
        self.assertTrue(Notification.objects.filter(source_key=source_key).exists())
        response = self.client.post(
            reverse("posts:follow", args=[self.author.username, 0])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Follow.objects.filter(follower=self.actor, following=self.author).exists()
        )
        self.assertFalse(
            Stream.objects.filter(user=self.actor, following=self.author).exists()
        )
        self.assertFalse(Notification.objects.filter(source_key=source_key).exists())

    def test_follow_fans_out_existing_and_new_global_posts_only(self):
        now = timezone.now()
        existing = [
            Post.objects.create(
                user=self.author,
                question_text=f"Global {index}",
                content="<p>Body</p>",
                posted_date=now - timedelta(minutes=index + 1),
            )
            for index in range(2)
        ]
        Post.objects.create(
            user=self.author,
            question_text="Future",
            content="<p>Body</p>",
            posted_date=now + timedelta(days=1),
        )
        dome = make_dome(self.author, title="Author private Dome")
        Post.objects.create(
            user=self.author,
            dome=dome,
            question_text="Dome only",
            content="<p>Body</p>",
        )

        self.assertEqual(
            self.client.post(
                reverse("posts:follow", args=[self.author.username, 1])
            ).status_code,
            302,
        )
        self.assertSetEqual(
            set(Stream.objects.filter(user=self.actor).values_list("post_id", flat=True)),
            {post.pk for post in existing},
        )

        new_global = Post.objects.create(
            user=self.author,
            question_text="New global",
            content="<p>Body</p>",
        )
        Post.objects.create(
            user=self.author,
            dome=dome,
            question_text="New Dome post",
            content="<p>Body</p>",
        )
        self.assertSetEqual(
            set(Stream.objects.filter(user=self.actor).values_list("post_id", flat=True)),
            {post.pk for post in existing} | {new_global.pk},
        )

    def test_stream_view_filters_inaccessible_private_rows(self):
        Follow.objects.create(follower=self.actor, following=self.author)
        public_post = Post.objects.create(
            user=self.author,
            question_text="Visible",
            content="<p>Body</p>",
        )
        dome = make_dome(self.author, title="Hidden Dome")
        private_post = Post.objects.create(
            user=self.author,
            dome=dome,
            question_text="Hidden",
            content="<p>Body</p>",
        )
        Stream.objects.create(
            user=self.actor,
            following=self.author,
            post=private_post,
            date=private_post.posted_date,
        )
        response = self.client.get(reverse("posts:stream"))
        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            {post.pk for post in response.context["latest_posts_list"]},
            {public_post.pk},
        )


class SocialCleanupMigrationTests(TransactionTestCase):
    migrate_from = ("posts", "0009_alter_post_picture")
    migrate_to = ("posts", "0012_private_post_media")

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_cleanup_deduplicates_social_rows_and_reconciles_like_counter(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldUser = old_apps.get_model("auth", "User")
        OldPost = old_apps.get_model("posts", "Post")
        OldLike = old_apps.get_model("posts", "Like")
        OldFollow = old_apps.get_model("posts", "Follow")
        OldStream = old_apps.get_model("posts", "Stream")

        author = OldUser.objects.create(username="cleanup-author")
        actor = OldUser.objects.create(username="cleanup-actor")
        post = OldPost.objects.create(
            user_id=author.pk,
            question_text="Cleanup",
            content="<p>Body</p>",
            likes=99,
            posted_date=timezone.now(),
        )
        OldLike.objects.create(user_id=actor.pk, post_id=post.pk)
        OldLike.objects.create(user_id=actor.pk, post_id=post.pk)
        OldFollow.objects.create(follower_id=actor.pk, following_id=author.pk)
        OldFollow.objects.create(follower_id=actor.pk, following_id=author.pk)
        OldFollow.objects.create(follower_id=actor.pk, following_id=actor.pk)
        OldStream.objects.create(
            user_id=actor.pk,
            following_id=author.pk,
            post_id=post.pk,
            date=post.posted_date,
        )
        OldStream.objects.create(
            user_id=actor.pk,
            following_id=author.pk,
            post_id=post.pk,
            date=post.posted_date,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewPost = new_apps.get_model("posts", "Post")
        NewLike = new_apps.get_model("posts", "Like")
        NewFollow = new_apps.get_model("posts", "Follow")
        NewStream = new_apps.get_model("posts", "Stream")
        self.assertEqual(NewLike.objects.filter(post_id=post.pk).count(), 1)
        self.assertEqual(NewPost.objects.get(pk=post.pk).likes, 1)
        self.assertEqual(
            NewFollow.objects.filter(follower_id=actor.pk, following_id=author.pk).count(),
            1,
        )
        self.assertFalse(
            NewFollow.objects.filter(follower_id=actor.pk, following_id=actor.pk).exists()
        )
        self.assertEqual(
            NewStream.objects.filter(user_id=actor.pk, post_id=post.pk).count(),
            1,
        )


@skipUnless(connection.vendor == "mysql", "MySQL concurrency coverage runs in CI")
class MySQLSocialConcurrencyTests(TransactionTestCase):
    def test_concurrent_duplicate_like_is_rejected_by_database_constraint(self):
        owner = User.objects.create_user("mysql-owner", password="x")
        actor = User.objects.create_user("mysql-actor", password="x")
        post = Post.objects.create(
            user=owner,
            question_text="Concurrent invariant",
            content="<p>Body</p>",
        )
        barrier = Barrier(2)

        def create_like():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    with transaction.atomic():
                        Like.objects.create(user_id=actor.pk, post_id=post.pk)
                    return True
                except IntegrityError:
                    return False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_like(), range(2)))

        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(Like.objects.filter(user=actor, post=post).count(), 1)
