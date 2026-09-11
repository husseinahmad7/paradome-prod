import Domes.storage
from django.db import migrations, models
import posts.models


class Migration(migrations.Migration):
    dependencies = [("posts", "0011_social_constraints")]

    operations = [
        migrations.AlterField(
            model_name="post",
            name="picture",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=Domes.storage.PrivateMediaStorage(),
                upload_to=posts.models.user_directory_path,
                validators=[posts.models.validate_image],
            ),
        ),
    ]
