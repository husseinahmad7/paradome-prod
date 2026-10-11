from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, override_settings

from .storage import PrivateMediaStorage


@override_settings(PRIVATE_MEDIA_EXCLUSIVE_SAVE=True)
class WasmerPrivateStorageTests(SimpleTestCase):
    def test_image_save_works_without_advisory_locks_and_has_no_public_url(self):
        with TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=directory):
            storage = PrivateMediaStorage()
            with patch("django.core.files.locks.lock", side_effect=OSError("unsupported")), \
                    patch("django.core.files.locks.unlock", side_effect=OSError("unsupported")):
                name = storage.save("posts/probe.png", ContentFile(b"synthetic image bytes"))
            self.assertEqual(Path(storage.path(name)).read_bytes(), b"synthetic image bytes")
            with self.assertRaises(ValueError):
                storage.url(name)

    def test_a_filename_race_does_not_overwrite_the_first_writer(self):
        with TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=directory):
            storage = PrivateMediaStorage()
            Path(directory, "race.png").write_bytes(b"first writer")
            # Simulate a file arriving after Storage.save's availability check.
            with patch.object(storage, "get_available_name", side_effect=["race.png", "retry.png"]):
                name = storage.save("race.png", ContentFile(b"second writer"))
            self.assertEqual(name, "retry.png")
            self.assertEqual(Path(directory, "race.png").read_bytes(), b"first writer")
            self.assertEqual(Path(directory, name).read_bytes(), b"second writer")

    def test_failed_write_removes_only_its_own_partial_file(self):
        class BrokenUpload(ContentFile):
            def chunks(self, chunk_size=None):
                yield b"partial"
                raise OSError("upload interrupted")

        with TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=directory):
            Path(directory, "other.png").write_bytes(b"keep")
            storage = PrivateMediaStorage()
            with self.assertRaisesRegex(OSError, "upload interrupted"):
                storage.save("partial.png", BrokenUpload(b""))
            self.assertFalse(Path(directory, "partial.png").exists())
            self.assertEqual(Path(directory, "other.png").read_bytes(), b"keep")
