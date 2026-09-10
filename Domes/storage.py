import warnings
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError


IMAGE_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """Filesystem storage that deliberately has no public URL."""

    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)

    def url(self, name):
        raise ValueError("Private media must be served by an authorized view.")


private_media_storage = PrivateMediaStorage()


def open_private_or_legacy(field_file):
    """Read protected storage, falling back during the one-time media move."""

    try:
        return field_file.storage.open(field_file.name, "rb")
    except (FileNotFoundError, OSError):
        legacy = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=None)
        return legacy.open(field_file.name, "rb")


def open_validated_image(
    field_file,
    *,
    max_bytes,
    max_width,
    max_height,
    max_pixels,
):
    """Open an image and derive its response MIME from decoded bytes.

    Legacy media is validated on every protected read as well as new uploads,
    so a misleading database filename can never choose a browser-executable
    Content-Type.
    """

    handle = open_private_or_legacy(field_file)
    try:
        handle.seek(0, 2)
        byte_size = handle.tell()
        handle.seek(0)
        if byte_size > max_bytes:
            raise ValueError("Image exceeds the protected-delivery size limit.")

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(handle)
            decoded_format = (image.format or "").upper()
            width, height = image.size
            image.verify()

        content_type = IMAGE_CONTENT_TYPES.get(decoded_format)
        if content_type is None:
            raise ValueError("Unsupported protected image format.")
        if (
            width > max_width
            or height > max_height
            or width * height > max_pixels
        ):
            raise ValueError("Image exceeds protected-delivery dimensions.")
        handle.seek(0)
        return handle, content_type
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        handle.close()
        raise OSError("Invalid protected image.") from exc


def safe_image_filename(name, content_type):
    """Return a header-safe filename with an extension matching decoded data."""

    stem = Path(name).stem
    stem = "".join(
        character for character in stem if character.isalnum() or character in "-_"
    )[:80]
    return f"{stem or 'image'}{IMAGE_EXTENSIONS[content_type]}"
