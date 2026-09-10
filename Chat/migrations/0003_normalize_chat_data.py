from django.db import migrations
from django.db.models import Count, Q


def normalize_chat_data(apps, schema_editor):
    ChatChannel = apps.get_model("Chat", "ChatChannel")
    ChatMessage = apps.get_model("Chat", "ChatMessage")

    ChatMessage.objects.filter(Q(body__isnull=True) | Q(body="")).update(
        body="[empty message]"
    )
    duplicates = (
        ChatChannel.objects.values("category_id", "title")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for duplicate in duplicates:
        ids = list(
            ChatChannel.objects.filter(
                category_id=duplicate["category_id"],
                title=duplicate["title"],
            )
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        keeper_id = ids[0]
        ChatMessage.objects.filter(channel_id__in=ids[1:]).update(
            channel_id=keeper_id
        )
        ChatChannel.objects.filter(pk__in=ids[1:]).delete()


class Migration(migrations.Migration):
    dependencies = [("Chat", "0002_remove_chatmessage_file")]

    operations = [
        migrations.RunPython(normalize_chat_data, migrations.RunPython.noop),
    ]
