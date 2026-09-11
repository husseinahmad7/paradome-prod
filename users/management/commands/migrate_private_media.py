import hashlib
import hmac
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.management.base import BaseCommand, CommandError

from Domes.models import Dome
from posts.models import Post
from users.models import Profile


CHUNK_SIZE = 1024 * 1024


def _content_fingerprint(storage, name):
    digest = hashlib.sha256()
    size = 0
    with storage.open(name, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.digest()


def _storage_contents_match(source, destination, name):
    source_size, source_digest = _content_fingerprint(source, name)
    destination_size, destination_digest = _content_fingerprint(destination, name)
    return source_size == destination_size and hmac.compare_digest(
        source_digest, destination_digest
    )


def _copy_chunks(source, destination):
    while True:
        chunk = source.read(CHUNK_SIZE)
        if not chunk:
            break
        destination.write(chunk)


def _replace_atomically(source_storage, destination_storage, name):
    destination_path = Path(destination_storage.path(name))
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = None
            with source_storage.open(name, "rb") as source:
                _copy_chunks(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_path, destination_path)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise


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
        replacements = []
        already_private = 0
        missing = []
        for name in sorted(names):
            if not legacy.exists(name):
                missing.append(name)
                continue
            if not private.exists(name):
                pending.append(name)
            elif _storage_contents_match(legacy, private, name):
                already_private += 1
            else:
                replacements.append(name)

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

        replaced = 0
        for name in replacements:
            if options["apply"]:
                try:
                    _replace_atomically(legacy, private, name)
                except OSError as error:
                    raise CommandError(
                        f"Could not atomically replace private upload {name}: {error}"
                    ) from error
            replaced += 1

        verb = "copied" if options["apply"] else "would copy"
        replacement_verb = "replaced" if options["apply"] else "would replace"
        self.stdout.write(
            f"{verb} {copied}; already private {already_private}; missing 0. "
            f"{replacement_verb} {replaced}. "
            "Legacy files were not deleted."
        )
