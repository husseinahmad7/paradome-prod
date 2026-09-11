from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Domes", "0008_dome_constraints")]

    operations = [
        migrations.CreateModel(
            name="RateLimitBucket",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("subject_hash", models.CharField(max_length=64)),
                ("window_start", models.PositiveBigIntegerField()),
                ("count", models.PositiveIntegerField(default=1)),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("subject_hash", "window_start"),
                        name="domes_ratelimit_subject_window_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("count__gte", 1)),
                        name="domes_ratelimit_count_positive",
                    ),
                ],
            },
        ),
    ]
