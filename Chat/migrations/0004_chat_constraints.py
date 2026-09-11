from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Chat", "0003_normalize_chat_data")]

    operations = [
        migrations.AlterField(
            model_name="chatmessage",
            name="body",
            field=models.TextField(max_length=1500),
        ),
        migrations.AddConstraint(
            model_name="chatchannel",
            constraint=models.UniqueConstraint(
                fields=("category", "title"),
                name="chat_channel_unique_title",
            ),
        ),
    ]
