from django.db import migrations
from django.db.models import Q


def normalize_message_bodies(apps, schema_editor):
    Message = apps.get_model("chat_messages", "Message")
    Message.objects.filter(Q(body__isnull=True) | Q(body="")).update(
        body="[empty message]"
    )


class Migration(migrations.Migration):
    dependencies = [("chat_messages", "0001_initial")]

    operations = [
        migrations.RunPython(normalize_message_bodies, migrations.RunPython.noop),
    ]
