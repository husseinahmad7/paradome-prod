import datetime
from pathlib import Path
from uuid import uuid4

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django_prose_editor.fields import ProseEditorField
from PIL import Image, UnidentifiedImageError

from Domes.access import DEMO_GROUP_NAME
from Domes.models import Dome
from Domes.storage import private_media_storage
from posts.sanitizers import sanitize_rich_text

def user_directory_path(instance,filename):
    suffix = Path(filename).suffix.lower()[:10]
    return f'posts/user_{instance.user_id}/{uuid4().hex}{suffix}'

def validate_image(fieldfile_obj):
    if not fieldfile_obj:
        return
    if fieldfile_obj.size > 4 * 1024 * 1024:
        raise ValidationError("Image files must be 4 MB or smaller.")
    content_type = getattr(fieldfile_obj, "content_type", "")
    allowed_formats = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }
    try:
        position = fieldfile_obj.tell()
        image = Image.open(fieldfile_obj)
        decoded_format = (image.format or "").upper()
        width, height = image.size
        image.verify()
        fieldfile_obj.seek(position)
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise ValidationError("Upload a valid image file.") from exc
    if decoded_format not in allowed_formats:
        raise ValidationError("Only JPEG, PNG, and WebP images are allowed.")
    if content_type and content_type != allowed_formats[decoded_format]:
        raise ValidationError("The declared image type does not match its contents.")
    if width * height > 20_000_000 or width > 6000 or height > 6000:
        raise ValidationError("Image dimensions are too large.")


PROSE_EXTENSIONS = {
    "Bold": True,
    "Italic": True,
    "Strike": True,
    "Underline": True,
    "Blockquote": True,
    "BulletList": True,
    "OrderedList": True,
    "ListItem": True,
    "Heading": {"levels": [2, 3, 4]},
    "Link": True,
    "Code": True,
    "CodeBlock": True,
}
class Tag(models.Model):
    title = models.CharField(max_length=75, verbose_name='Tag')
    slug = models.SlugField(null=False, unique=True)
    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'tags'
    def get_absolute_url(self):
        return f"{reverse('posts:index')}?question_text=&tags={self.pk}"
    def __str__(self):
        return self.title
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        return super().save(*args, **kwargs)

class Post(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    question_text = models.CharField(max_length=200)
    content = ProseEditorField(extensions=PROSE_EXTENSIONS, sanitize=True)
    # content = models.TextField(max_length=2000)
    picture = models.ImageField(
        upload_to=user_directory_path,
        storage=private_media_storage,
        null=True,
        blank=True,
        validators=[validate_image],
    )
    likes = models.IntegerField(default=0)
    tags = models.ManyToManyField(Tag, related_name="tags", blank=True)
    posted_date = models.DateTimeField(default=timezone.now)
    dome = models.ForeignKey(Dome, on_delete=models.CASCADE,related_name= 'posts',null=True, blank=True)
    
    def __str__(self):
        return self.question_text
    @admin.display(
        boolean=True,
        ordering='posted_date',
        description='Posted recently?',
    )
    
    def was_posted_recently(self):
        return self.posted_date >= timezone.now() - datetime.timedelta(days=1)
    def get_absolute_url(self):
        return reverse('posts:post-detail', kwargs={'pk':self.pk})

    def save(self, *args, **kwargs):
        self.content = sanitize_rich_text(self.content)
        return super().save(*args, **kwargs)
    @property
    def comment_count(self):
        return Comment.objects.filter(post=self).count()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(likes__gte=0),
                name="posts_post_likes_nonnegative",
            ),
        ]
    


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='comments', on_delete=models.CASCADE)
    comment = ProseEditorField(extensions=PROSE_EXTENSIONS, sanitize=True)
    commented = models.DateTimeField(auto_now_add=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, related_name='replied_to', on_delete=models.CASCADE)
    
    #approved boolean def approved(self): self.approved = True self.save()
    def __str__(self):
        return f"{self.post.question_text} -- {self.comment[:20]} -- by {self.user}"
    def save(self, *args, **kwargs):
        if self.reply_to_id and self.reply_to.post_id != self.post_id:
            raise ValidationError("A reply must belong to the same post.")
        self.comment = sanitize_rich_text(self.comment)
        return super().save(*args, **kwargs)
    class Meta:
         get_latest_by='-commented'
         ordering = ['-commented']
        
    @property 
    def children(self):
        return Comment.objects.filter(reply_to=self)
    
    @property
    def is_parent(self):
        if self.reply_to is None:
            return True
        return False

class Follow(models.Model):
    follower = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follower")
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="following")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["follower", "following"],
                name="posts_follow_unique_pair",
            ),
            models.CheckConstraint(
                condition=~Q(follower=models.F("following")),
                name="posts_follow_no_self",
            ),
        ]

class Stream(models.Model):
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stream_following")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    date = models.DateTimeField()
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "post"],
                name="posts_stream_unique_user_post",
            ),
        ]
            
class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_likes")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='post_likes')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "post"],
                name="posts_like_unique_user_post",
            ),
        ]


def add_post_to_followers(sender, instance, created, **kwargs):
    if not created or instance.dome_id is not None:
        return
    if instance.user.groups.filter(name=DEMO_GROUP_NAME).exists():
        return
    followers = Follow.objects.filter(following=instance.user).exclude(
        follower__groups__name=DEMO_GROUP_NAME
    )
    Stream.objects.bulk_create(
        [
            Stream(
                post=instance,
                user=follow.follower,
                following=instance.user,
                date=instance.posted_date,
            )
            for follow in followers.select_related("follower")
        ],
        ignore_conflicts=True,
    )


post_save.connect(
    add_post_to_followers,
    sender=Post,
    dispatch_uid="posts.add_post_to_followers",
)
