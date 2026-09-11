from pathlib import Path
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.text import slugify
from PIL import Image, UnidentifiedImageError

from .storage import private_media_storage




def generate_random():
    from django.utils.crypto import get_random_string
    string = get_random_string(length=11)
    number = 1
    while Dome.objects.filter(invitationstr=string).exists():
        string = f'{string}{number}'
        number += 1
    return string

def dome_directory_path_banner(instance, filename):
    suffix = Path(filename).suffix.lower()[:10]
    return f"user_{instance.user_id}/domes/banner-{uuid4().hex}{suffix}"

def dome_directory_path_picture(instance, filename):
    suffix = Path(filename).suffix.lower()[:10]
    return f"user_{instance.user_id}/domes/icon-{uuid4().hex}{suffix}"


def validate_dome_image(upload):
    if not upload:
        return
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError("Image files must be 5 MB or smaller.")
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
    if width * height > 24_000_000 or width > 7000 or height > 7000:
        raise ValidationError("Image dimensions are too large.")


class Dome(models.Model):
    icon = models.ImageField(upload_to=dome_directory_path_picture, storage=private_media_storage, validators=[validate_dome_image], blank=True, null=True)
    banner = models.ImageField(upload_to=dome_directory_path_banner, storage=private_media_storage, validators=[validate_dome_image], blank=True, null=True)
    title = models.CharField(max_length=25, null=False, blank=False)
    description = models.CharField(max_length=144, null=False, blank=False)
    date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='server_owner')
    members = models.ManyToManyField(User, related_name='dome_members', blank=True)
    moderators = models.ManyToManyField(User, related_name='dome_moderators', blank=True)
    # categories = models.ManyToManyField(Category)
    PRIVACY_CHOICES = ((1,'Public'), (0,'Private'),)
    privacy = models.IntegerField(choices=PRIVACY_CHOICES, default=1)
    invitationstr = models.CharField(default=generate_random, max_length=13, unique=True)

    def __str__(self):
        return self.title
    def get_absolute_url(self):
        return reverse('domes:dome-detail', kwargs={'pk':self.pk})
    def get_invitation_link(self):
        slug = slugify(self.title)
        return reverse('domes:dome-invitation', kwargs={'slug': slug,'code':self.invitationstr})
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(privacy__in=(0, 1)),
                name="domes_dome_valid_privacy",
            ),
        ]

class Category(models.Model):
    title = models.CharField(max_length=35)
    # text_channels = models.ManyToManyField(TextChannels)
    Dome = models.ForeignKey(Dome,related_name='categories',on_delete=models.CASCADE)

    def __str__(self):
        return self.title

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["Dome", "title"],
                name="domes_category_unique_title",
            ),
        ]


class RateLimitBucket(models.Model):
    """A privacy-safe counter for one subject and fixed time window."""

    subject_hash = models.CharField(max_length=64)
    window_start = models.PositiveBigIntegerField()
    count = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subject_hash", "window_start"],
                name="domes_ratelimit_subject_window_unique",
            ),
            models.CheckConstraint(
                condition=Q(count__gte=1),
                name="domes_ratelimit_count_positive",
            ),
        ]


# class DomeMembership(models.Model):
#     class Access(models.IntegerChoices):
#         MEMBER = 1            # Can view and create and move only own items
#         ADMIN = 2             # Can remove members and modify project settings.

#     dome = models.ForeignKey(
#         Dome, on_delete=models.CASCADE)
#     member = models.ForeignKey(
#         User, on_delete=models.CASCADE)
#     access_level = models.IntegerField(choices=Access.choices, default=1)
#     # created_at = models.DateTimeField(default=timezone.now)

#     def __str__(self):
#         return f'{self.member.user_name} , {self.dome.title}'

#     class Meta:
#         unique_together = ('dome', 'member')

# class Attachment(models.Model):
#     item = models.ForeignKey(
#         Category, on_delete=models.CASCADE, related_name='attachments')
#     upload = models.FileField(upload_to='attachments')
