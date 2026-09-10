from django.db import migrations, models
import users.models
import Domes.storage


class Migration(migrations.Migration):
    dependencies = [("users", "0002_alter_profile_favorite")]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="picture",
            field=models.ImageField(
                default="profile_pics/default.jpg",
                storage=Domes.storage.PrivateMediaStorage(),
                upload_to=users.models.profile_pic_path,
                validators=[users.models.validate_profile_image],
            ),
        ),
    ]
