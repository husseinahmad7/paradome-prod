from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("posts", "0010_dedupe_social_data")]

    operations = [
        migrations.AddConstraint(
            model_name="post",
            constraint=models.CheckConstraint(
                condition=models.Q(("likes__gte", 0)),
                name="posts_post_likes_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="follow",
            constraint=models.UniqueConstraint(
                fields=("follower", "following"),
                name="posts_follow_unique_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="follow",
            constraint=models.CheckConstraint(
                condition=~models.Q(("follower", models.F("following"))),
                name="posts_follow_no_self",
            ),
        ),
        migrations.AddConstraint(
            model_name="stream",
            constraint=models.UniqueConstraint(
                fields=("user", "post"),
                name="posts_stream_unique_user_post",
            ),
        ),
        migrations.AddConstraint(
            model_name="like",
            constraint=models.UniqueConstraint(
                fields=("user", "post"),
                name="posts_like_unique_user_post",
            ),
        ),
    ]
