from django.db import migrations
from django.db.models import Count
from django.utils.crypto import get_random_string


def _unique_invitation(Dome):
    value = get_random_string(11)
    while Dome.objects.filter(invitationstr=value).exists():
        value = get_random_string(11)
    return value


def normalize_unique_values(apps, schema_editor):
    Dome = apps.get_model("Domes", "Dome")
    Category = apps.get_model("Domes", "Category")

    seen = set()
    for dome in Dome.objects.order_by("pk").iterator():
        value = dome.invitationstr
        if not value or value in seen:
            value = _unique_invitation(Dome)
            Dome.objects.filter(pk=dome.pk).update(invitationstr=value)
        seen.add(value)

    duplicate_groups = (
        Category.objects.values("Dome_id", "title")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for duplicate in duplicate_groups:
        categories = list(
            Category.objects.filter(
                Dome_id=duplicate["Dome_id"], title=duplicate["title"]
            ).order_by("pk")
        )
        for ordinal, category in enumerate(categories[1:], start=2):
            suffix = f" ({ordinal})"
            base = duplicate["title"][: 35 - len(suffix)]
            candidate = f"{base}{suffix}"
            while Category.objects.filter(
                Dome_id=duplicate["Dome_id"], title=candidate
            ).exclude(pk=category.pk).exists():
                ordinal += 1
                suffix = f" ({ordinal})"
                candidate = f"{duplicate['title'][: 35 - len(suffix)]}{suffix}"
            Category.objects.filter(pk=category.pk).update(title=candidate)


class Migration(migrations.Migration):
    dependencies = [("Domes", "0006_rename_picture_dome_icon")]

    operations = [
        migrations.RunPython(normalize_unique_values, migrations.RunPython.noop),
    ]
