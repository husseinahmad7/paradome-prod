from django.db import migrations, models
from django.db.models import F


LEGACY_EXPIRY_PADDING_SECONDS = 24 * 60 * 60


def populate_legacy_expiration(apps, schema_editor):
    RateLimitBucket = apps.get_model("Domes", "RateLimitBucket")
    RateLimitBucket.objects.filter(expires_at__isnull=True).update(
        expires_at=F("window_start") + LEGACY_EXPIRY_PADDING_SECONDS
    )


class Migration(migrations.Migration):
    dependencies = [("Domes", "0009_ratelimitbucket")]

    operations = [
        migrations.AddField(
            model_name="ratelimitbucket",
            name="expires_at",
            field=models.PositiveBigIntegerField(db_index=True, null=True),
        ),
        migrations.RunPython(
            populate_legacy_expiration,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="ratelimitbucket",
            name="expires_at",
            field=models.PositiveBigIntegerField(db_index=True),
        ),
    ]
