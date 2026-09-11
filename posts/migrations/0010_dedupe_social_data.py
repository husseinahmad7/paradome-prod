from django.db import migrations
from django.db.models import Count


def dedupe_social_data(apps, schema_editor):
    Like = apps.get_model("posts", "Like")
    Follow = apps.get_model("posts", "Follow")
    Stream = apps.get_model("posts", "Stream")
    Post = apps.get_model("posts", "Post")

    for duplicate in (
        Like.objects.values("user_id", "post_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    ):
        ids = list(
            Like.objects.filter(
                user_id=duplicate["user_id"], post_id=duplicate["post_id"]
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        Like.objects.filter(pk__in=ids[1:]).delete()

    Follow.objects.filter(follower_id=models_f("following_id")).delete()
    for duplicate in (
        Follow.objects.values("follower_id", "following_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    ):
        ids = list(
            Follow.objects.filter(
                follower_id=duplicate["follower_id"],
                following_id=duplicate["following_id"],
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        Follow.objects.filter(pk__in=ids[1:]).delete()

    for duplicate in (
        Stream.objects.values("user_id", "post_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    ):
        ids = list(
            Stream.objects.filter(
                user_id=duplicate["user_id"], post_id=duplicate["post_id"]
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        Stream.objects.filter(pk__in=ids[1:]).delete()

    for post in Post.objects.all().iterator():
        Post.objects.filter(pk=post.pk).update(
            likes=Like.objects.filter(post_id=post.pk).count()
        )


def models_f(field_name):
    from django.db.models import F

    return F(field_name)


class Migration(migrations.Migration):
    dependencies = [("posts", "0009_alter_post_picture")]

    operations = [
        migrations.RunPython(dedupe_social_data, migrations.RunPython.noop),
    ]
