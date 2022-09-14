from django.core.files.base import File
from django.db import models
from django.contrib.auth.models import User
from PIL import Image
from posts.models import Post
import os
from django.conf import settings

def profile_pic_path(instance, filename):
    pic_path = f'profile_pics/user_{instance.user.id}.jpg'
    full_path = os.path.join(settings.MEDIA_ROOT, pic_path)
    
    if os.path.exists(full_path):
        os.remove(full_path)
    return pic_path

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    bio = models.CharField(max_length=200, blank=True)
    picture = models.ImageField(default='profile_pics/default.jpg', upload_to=profile_pic_path)
    favorite = models.ManyToManyField(Post, blank=True)
    
    def __str__(self):
        return f'{self.user.username} Profile'
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.picture:
            old = self.picture.path
            img = Image.open(self.picture.path)
            if img.height > 300 and img.width > 300:
                output_size = (300,300)
                img.thumbnail(output_size)
                img.save(self.picture.path)
        
            # dont forget to delete the old images