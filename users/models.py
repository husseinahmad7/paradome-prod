from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from PIL import Image, UnidentifiedImageError

from posts.models import Post
from Domes.storage import private_media_storage

def profile_pic_path(instance, filename):
    suffix = Path(filename).suffix.lower()[:10]
    return f"profile_pics/user_{instance.user_id}/{uuid4().hex}{suffix}"


def validate_profile_image(upload):
    if not upload:
        return
    if upload.size > 4 * 1024 * 1024:
        raise ValidationError("Profile images must be 4 MB or smaller.")
    content_type = getattr(upload, "content_type", "")
    allowed_formats = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }
    try:
        position = upload.tell()
        image = Image.open(upload)
        decoded_format = (image.format or "").upper()
        width, height = image.size
        image.verify()
        upload.seek(position)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ValidationError("Upload a valid image file.") from exc
    if decoded_format not in allowed_formats:
        raise ValidationError("Only JPEG, PNG, and WebP images are allowed.")
    if content_type and content_type != allowed_formats[decoded_format]:
        raise ValidationError("The declared image type does not match its contents.")
    if width * height > 16_000_000 or width > 5000 or height > 5000:
        raise ValidationError("Image dimensions are too large.")

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    bio = models.CharField(max_length=200, blank=True)
    picture = models.ImageField(
        default='profile_pics/default.jpg',
        upload_to=profile_pic_path,
        storage=private_media_storage,
        validators=[validate_profile_image],
    )
    favorite = models.ManyToManyField(Post, blank=True)
    
    def __str__(self):
        return f'{self.user.username} Profile'
