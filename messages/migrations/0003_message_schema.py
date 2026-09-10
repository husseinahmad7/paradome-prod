from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat_messages", "0002_normalize_message_bodies")]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="body",
            field=models.TextField(max_length=1000),
        ),
        migrations.AddIndex(
            model_name="message",
            index=models.Index(
                fields=["user", "recipient", "-date"],
                name="dm_conversation_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="message",
            index=models.Index(
                fields=["user", "is_read"],
                name="dm_unread_idx",
            ),
        ),
    ]
