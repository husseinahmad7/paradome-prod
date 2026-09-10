from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand

from Domes.models import Dome
from Domes.storage import private_media_storage
from posts.models import Post
from users.models import Profile


class Command(BaseCommand):
    help = "Copy referenced legacy uploads into protected storage without deleting originals."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        legacy = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=None)
        names = set()
        for dome in Dome.objects.only("icon", "banner").iterator():
            if dome.icon:
                names.add(dome.icon.name)
            if dome.banner:
                names.add(dome.banner.name)
        names.update(
            Post.objects.exclude(picture="").exclude(picture__isnull=True)
            .values_list("picture", flat=True)
        )
        names.update(
            Profile.objects.exclude(picture="").values_list("picture", flat=True)
        )

        copied = already_private = missing = 0
        for name in sorted(names):
            if private_media_storage.exists(name):
                already_private += 1
                continue
            if not legacy.exists(name):
                missing += 1
                self.stderr.write(f"missing legacy upload: {name}")
                continue
            if options["apply"]:
                with legacy.open(name, "rb") as source:
                    saved_name = private_media_storage.save(name, File(source))
                if saved_name != name:
                    raise RuntimeError(
                        f"Private media collision for {name}; wrote {saved_name}."
                    )
            copied += 1

        verb = "copied" if options["apply"] else "would copy"
        self.stdout.write(
            f"{verb} {copied}; already private {already_private}; missing {missing}. "
            "Legacy files were not deleted."
        )
