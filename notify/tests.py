from django.contrib.auth.models import Group, User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from posts.models import Comment, Follow, Like, Post

from .models import Notification
from .views import CountNotifications


class NotificationSignalTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user("author", password="x")
        self.actor = User.objects.create_user("actor", password="x")
        self.post = Post.objects.create(
            user=self.author,
            question_text="Question",
            content="<p>Body</p>",
        )

    def test_like_signal_only_creates_once(self):
        like = Like.objects.create(user=self.actor, post=self.post)
        self.assertEqual(Notification.objects.filter(notification_type=1).count(), 1)
        like.save()
        self.assertEqual(Notification.objects.filter(notification_type=1).count(), 1)
        like.delete()
        self.assertFalse(Notification.objects.filter(notification_type=1).exists())

    def test_comment_preview_is_plain_text_and_created_aware(self):
        comment = Comment.objects.create(
            user=self.actor,
            post=self.post,
            comment="<p><strong>Hello</strong></p>",
        )
        notification = Notification.objects.get(notification_type=2)
        self.assertIn("Hello", notification.text_preview)
        self.assertNotIn("<strong>", notification.text_preview)
        comment.save()
        self.assertEqual(Notification.objects.filter(notification_type=2).count(), 1)

    def test_identical_comments_have_independent_notification_identity(self):
        first = Comment.objects.create(
            user=self.actor,
            post=self.post,
            comment="<p>Same text</p>",
        )
        second = Comment.objects.create(
            user=self.actor,
            post=self.post,
            comment="<p>Same text</p>",
        )

        notifications = Notification.objects.filter(notification_type=2)
        self.assertEqual(notifications.count(), 2)
        self.assertSetEqual(
            set(notifications.values_list("source_key", flat=True)),
            {f"comment:{first.pk}", f"comment:{second.pk}"},
        )

        first.delete()
        self.assertFalse(
            Notification.objects.filter(source_key=f"comment:{first.pk}").exists()
        )
        self.assertTrue(
            Notification.objects.filter(source_key=f"comment:{second.pk}").exists()
        )

    def test_self_and_demo_actions_do_not_notify(self):
        Like.objects.create(user=self.author, post=self.post)
        self.assertFalse(Notification.objects.exists())
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo")
        demo.groups.add(demo_group)
        Follow.objects.create(follower=demo, following=self.author)
        self.assertFalse(Notification.objects.exists())

    def test_follow_signal_creates_once_and_delete_removes_its_notification(self):
        follow = Follow.objects.create(follower=self.actor, following=self.author)
        source_key = f"follow:{follow.pk}"
        self.assertEqual(
            Notification.objects.filter(
                source_key=source_key,
                notification_type=3,
                sender=self.actor,
                user=self.author,
            ).count(),
            1,
        )
        follow.save()
        self.assertEqual(Notification.objects.filter(source_key=source_key).count(), 1)
        follow.delete()
        self.assertFalse(Notification.objects.filter(source_key=source_key).exists())

    def test_real_users_do_not_notify_demo_recipients(self):
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo-recipient")
        demo.groups.add(demo_group)
        Follow.objects.create(follower=self.actor, following=demo)
        self.assertFalse(Notification.objects.filter(user=demo).exists())


class NotificationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="x")
        self.sender = User.objects.create_user("sender", password="x")
        self.notification = Notification.objects.create(
            user=self.user,
            sender=self.sender,
            notification_type=3,
            text_preview="is following you",
        )

    def test_list_requires_authentication(self):
        response = self.client.get(reverse("notify:notification"))
        self.assertEqual(response.status_code, 302)

    def test_delete_is_post_only_and_owner_scoped(self):
        url = reverse("notify:del", args=[self.notification.pk])
        self.client.force_login(self.sender)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Notification.objects.filter(pk=self.notification.pk).exists())

    def test_list_is_owner_scoped_and_count_only_includes_unseen_rows(self):
        seen = Notification.objects.create(
            user=self.user,
            sender=self.sender,
            notification_type=3,
            text_preview="older relationship update",
            is_seen=True,
        )
        other = User.objects.create_user("other", password="x")
        Notification.objects.create(
            user=other,
            sender=self.sender,
            notification_type=3,
            text_preview="must stay private",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("notify:notification"))
        self.assertEqual(response.status_code, 200)
        self.assertSetEqual(
            {
                notification.pk
                for notification in response.context["notifications"]
            },
            {seen.pk, self.notification.pk},
        )
        self.assertEqual(CountNotifications(response.wsgi_request)["notify_count"], 1)
        self.notification.is_seen = True
        self.notification.save(update_fields=["is_seen"])
        self.assertEqual(CountNotifications(response.wsgi_request)["notify_count"], 0)

    def test_demo_notification_list_is_forbidden_and_count_is_zero(self):
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo-viewer")
        demo.groups.add(demo_group)
        Notification.objects.create(
            user=demo,
            sender=self.sender,
            notification_type=3,
            text_preview="legacy row",
        )
        self.client.force_login(demo)
        self.assertEqual(
            self.client.get(reverse("notify:notification")).status_code,
            403,
        )
        request = RequestFactory().get("/notifications/")
        request.user = demo
        self.assertEqual(CountNotifications(request)["notify_count"], 0)


class NotificationSourceMigrationTests(TransactionTestCase):
    migrate_from = ("notify", "0002_alter_notification_text_preview")
    migrate_to = ("notify", "0003_notification_source_identity")

    def test_comment_rows_are_reconstructed_by_identity_not_position(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        OldUser = old_apps.get_model("auth", "User")
        OldPost = old_apps.get_model("posts", "Post")
        OldComment = old_apps.get_model("posts", "Comment")
        OldNotification = old_apps.get_model("notify", "Notification")

        author = OldUser.objects.create(username="migration-author")
        actor = OldUser.objects.create(username="migration-actor")
        post = OldPost.objects.create(
            user_id=author.pk,
            question_text="Migration question",
            content="<p>Body</p>",
        )
        first = OldComment.objects.create(
            user_id=actor.pk,
            post_id=post.pk,
            comment="<p><strong>First</strong></p>",
        )
        second = OldComment.objects.create(
            user_id=actor.pk,
            post_id=post.pk,
            comment="<p>Second</p>",
        )

        # Deliberately reverse legacy insertion order. A positional backfill
        # would attach these texts and seen flags to the wrong comments.
        OldNotification.objects.create(
            post_id=post.pk,
            sender_id=actor.pk,
            user_id=author.pk,
            notification_type=2,
            text_preview=(
                'commented on your post "Migration question": <p>Second</p>'
            ),
            is_seen=False,
        )
        OldNotification.objects.create(
            post_id=post.pk,
            sender_id=actor.pk,
            user_id=author.pk,
            notification_type=2,
            text_preview=(
                'commented on your post "Migration question": '
                "<p><strong>First</strong></p>"
            ),
            is_seen=True,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewNotification = new_apps.get_model("notify", "Notification")

        first_notification = NewNotification.objects.get(
            source_key=f"comment:{first.pk}"
        )
        second_notification = NewNotification.objects.get(
            source_key=f"comment:{second.pk}"
        )
        self.assertTrue(first_notification.is_seen)
        self.assertIn(": First", first_notification.text_preview)
        self.assertNotIn("<strong>", first_notification.text_preview)
        self.assertFalse(second_notification.is_seen)
        self.assertIn(": Second", second_notification.text_preview)
