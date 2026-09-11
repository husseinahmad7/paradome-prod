from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand, CommandError

from Domes.models import Dome
from posts.models import Post
from users.models import Profile


class Command(BaseCommand):
    help = "Copy referenced legacy uploads into protected storage without deleting originals."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--source-root",
            help="Absolute legacy media directory (defaults to MEDIA_ROOT).",
        )

    def handle(self, *args, **options):
        source_root = Path(options["source_root"] or settings.MEDIA_ROOT).expanduser()
        if not source_root.is_absolute():
            raise CommandError("--source-root must be an absolute path.")
        if not source_root.exists():
            raise CommandError(f"Source media directory does not exist: {source_root}")
        if not source_root.is_dir():
            raise CommandError(f"Source media path is not a directory: {source_root}")

        source_root = source_root.resolve()
        private_root = Path(settings.PRIVATE_MEDIA_ROOT).expanduser().resolve()
        if source_root == private_root:
            raise CommandError("Source and private media directories must be different.")

        legacy = FileSystemStorage(location=source_root, base_url=None)
        private = FileSystemStorage(location=private_root, base_url=None)
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

        pending = []
        already_private = 0
        missing = []
        for name in sorted(names):
            if private.exists(name):
                already_private += 1
                continue
            if not legacy.exists(name):
                missing.append(name)
                continue
            pending.append(name)

        if missing:
            for name in missing:
                self.stderr.write(f"missing legacy upload: {name}")
            raise CommandError(
                f"Migration aborted before copying because {len(missing)} "
                "referenced upload(s) are missing."
            )

        copied = 0
        for name in pending:
            if options["apply"]:
                with legacy.open(name, "rb") as source:
                    saved_name = private.save(name, File(source))
                if saved_name != name:
                    private.delete(saved_name)
                    raise CommandError(
                        f"Private media collision for {name}; wrote {saved_name}."
                    )
            copied += 1

        verb = "copied" if options["apply"] else "would copy"
        self.stdout.write(
            f"{verb} {copied}; already private {already_private}; missing 0. "
            "Legacy files were not deleted."
        )
