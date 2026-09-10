import Domes.models
import Domes.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("Domes", "0007_normalize_unique_values")]

    operations = [
        migrations.AlterField(
            model_name="dome",
            name="invitationstr",
            field=models.CharField(
                default=Domes.models.generate_random,
                max_length=13,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="dome",
            name="icon",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=Domes.storage.PrivateMediaStorage(),
                upload_to=Domes.models.dome_directory_path_picture,
                validators=[Domes.models.validate_dome_image],
            ),
        ),
        migrations.AlterField(
            model_name="dome",
            name="banner",
            field=models.ImageField(
                blank=True,
                null=True,
                storage=Domes.storage.PrivateMediaStorage(),
                upload_to=Domes.models.dome_directory_path_banner,
                validators=[Domes.models.validate_dome_image],
            ),
        ),
        migrations.AddConstraint(
            model_name="dome",
            constraint=models.CheckConstraint(
                condition=models.Q(("privacy__in", (0, 1))),
                name="domes_dome_valid_privacy",
            ),
        ),
        migrations.AddConstraint(
            model_name="category",
            constraint=models.UniqueConstraint(
                fields=("Dome", "title"),
                name="domes_category_unique_title",
            ),
        ),
    ]
