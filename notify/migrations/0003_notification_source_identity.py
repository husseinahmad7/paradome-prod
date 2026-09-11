from django.db import migrations, models
from django.utils.html import strip_tags


def _comment_preview(question_text, comment_body):
    text = strip_tags(comment_body).strip()[:89]
    return f'commented on your post "{question_text}": {text}'


def _legacy_comment_preview(question_text, comment_body):
    return f'commented on your post "{question_text}": {comment_body[:89]}'


def backfill_source_keys(apps, schema_editor):
    """Attach legacy notifications to their source rows and remove retries.

    The old signals created another Notification on every save. Likes and
    follows have an exact source match. Comment notifications are rebuilt
    deterministically from live Comment rows because the legacy schema stored
    no comment foreign key; matching legacy text is used only to retain a
    conservative seen state.
    """

    Notification = apps.get_model("notify", "Notification")
    Like = apps.get_model("posts", "Like")
    Follow = apps.get_model("posts", "Follow")
    Comment = apps.get_model("posts", "Comment")
    Dome = apps.get_model("Domes", "Dome")
    User = apps.get_model("auth", "User")

    for like in Like.objects.select_related("post").iterator():
        candidates = Notification.objects.filter(
            notification_type=1,
            post_id=like.post_id,
            sender_id=like.user_id,
            user_id=like.post.user_id,
        ).order_by("date", "pk")
        notification = candidates.first()
        if notification is None:
            continue
        notification.source_key = f"like:{like.pk}"
        notification.save(update_fields=["source_key"])
        candidates.exclude(pk=notification.pk).delete()

    for follow in Follow.objects.all().iterator():
        candidates = Notification.objects.filter(
            notification_type=3,
            post_id=None,
            sender_id=follow.follower_id,
            user_id=follow.following_id,
        ).order_by("date", "pk")
        notification = candidates.first()
        if notification is None:
            continue
        notification.source_key = f"follow:{follow.pk}"
        notification.save(update_fields=["source_key"])
        candidates.exclude(pk=notification.pk).delete()

    legacy_by_group = {}
    for notification in Notification.objects.filter(notification_type=2).values(
        "post_id",
        "sender_id",
        "user_id",
        "text_preview",
        "is_seen",
    ):
        key = (
            notification["post_id"],
            notification["sender_id"],
            notification["user_id"],
        )
        legacy_by_group.setdefault(key, []).append(notification)

    # Reconstructing avoids ever assigning one comment's text/identity to a
    # different row merely because two timestamps happened to sort together.
    Notification.objects.filter(notification_type=2).delete()
    demo_user_ids = set(
        User.objects.filter(groups__name="Demo").values_list("pk", flat=True)
    )
    demo_dome_ids = set(
        Dome.objects.filter(user_id__in=demo_user_ids).values_list("pk", flat=True)
    )

    for comment in Comment.objects.select_related("post").order_by("pk").iterator():
        recipient_id = comment.post.user_id
        if (
            comment.user_id == recipient_id
            or comment.user_id in demo_user_ids
            or recipient_id in demo_user_ids
            or comment.post.dome_id in demo_dome_ids
        ):
            continue

        clean_preview = _comment_preview(
            comment.post.question_text, comment.comment
        )
        possible_legacy_previews = {
            clean_preview,
            _legacy_comment_preview(
                comment.post.question_text, comment.comment
            ),
        }
        candidates = legacy_by_group.get(
            (comment.post_id, comment.user_id, recipient_id), []
        )
        exact_candidates = [
            candidate
            for candidate in candidates
            if candidate["text_preview"] in possible_legacy_previews
        ]
        # When duplicate legacy rows disagree, retaining unread is safer than
        # silently hiding a notification the recipient may not have seen.
        was_seen = bool(exact_candidates) and all(
            candidate["is_seen"] for candidate in exact_candidates
        )
        reconstructed = Notification.objects.create(
            post_id=comment.post_id,
            sender_id=comment.user_id,
            user_id=recipient_id,
            notification_type=2,
            source_key=f"comment:{comment.pk}",
            text_preview=clean_preview,
            is_seen=was_seen,
        )
        Notification.objects.filter(pk=reconstructed.pk).update(
            date=comment.commented
        )


class Migration(migrations.Migration):
    dependencies = [
        ("notify", "0002_alter_notification_text_preview"),
        ("posts", "0011_social_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="source_key",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RunPython(backfill_source_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notification",
            name="source_key",
            field=models.CharField(
                blank=True, max_length=64, null=True, unique=True
            ),
        ),
    ]
