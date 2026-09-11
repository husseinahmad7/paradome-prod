from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.html import strip_tags

from Domes.access import is_demo_owned_dome, is_demo_user
from posts.models import Comment, Follow, Like

from .models import Notification


def _may_notify(sender, recipient, post=None):
    if sender == recipient or is_demo_user(sender) or is_demo_user(recipient):
        return False
    if post is not None and post.dome_id and is_demo_owned_dome(post.dome):
        return False
    return True


def _create_notification(source_key, **fields):
    """Create at most one notification for a concrete source model row."""

    Notification.objects.get_or_create(source_key=source_key, defaults=fields)


@receiver(post_save, sender=Like, dispatch_uid="notify.like.created")
def user_liked_post(sender, instance, created, **kwargs):
    if not created or not _may_notify(instance.user, instance.post.user, instance.post):
        return
    _create_notification(
        f"like:{instance.pk}",
        post=instance.post,
        sender=instance.user,
        user=instance.post.user,
        notification_type=1,
        text_preview=f'liked your post "{instance.post.question_text}"',
    )


@receiver(post_delete, sender=Like, dispatch_uid="notify.like.deleted")
def user_disliked_post(sender, instance, **kwargs):
    Notification.objects.filter(source_key=f"like:{instance.pk}").delete()


@receiver(post_save, sender=Follow, dispatch_uid="notify.follow.created")
def user_follow(sender, instance, created, **kwargs):
    if not created or not _may_notify(instance.follower, instance.following):
        return
    _create_notification(
        f"follow:{instance.pk}",
        sender=instance.follower,
        user=instance.following,
        notification_type=3,
        post=None,
        text_preview="is following you",
    )


@receiver(post_delete, sender=Follow, dispatch_uid="notify.follow.deleted")
def user_unfollow(sender, instance, **kwargs):
    Notification.objects.filter(source_key=f"follow:{instance.pk}").delete()


def _comment_preview(comment):
    text = strip_tags(comment.comment).strip()[:89]
    return f'commented on your post "{comment.post.question_text}": {text}'


@receiver(post_save, sender=Comment, dispatch_uid="notify.comment.created")
def comment_add(sender, instance, created, **kwargs):
    if not created or not _may_notify(instance.user, instance.post.user, instance.post):
        return
    _create_notification(
        f"comment:{instance.pk}",
        post=instance.post,
        sender=instance.user,
        user=instance.post.user,
        notification_type=2,
        text_preview=_comment_preview(instance),
    )


@receiver(post_delete, sender=Comment, dispatch_uid="notify.comment.deleted")
def comment_delete(sender, instance, **kwargs):
    Notification.objects.filter(source_key=f"comment:{instance.pk}").delete()
