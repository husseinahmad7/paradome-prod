from django.db import models
from django.contrib.auth.models import User
import os
from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from PIL import Image




def generate_random():
    from django.utils.crypto import get_random_string
    string = get_random_string(length=11)
    number = 1
    while Dome.objects.filter(invitationstr=string).exists():
        string = f'{string}{number}'
        number += 1
    return string

def dome_directory_path_banner(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    banner_pic_name = 'user_{0}/domebanner_{1}'.format(instance.user.id, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, banner_pic_name)

    if os.path.exists(full_path):
        os.remove(full_path)
    return banner_pic_name

def dome_directory_path_picture(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    picture_pic_name = 'user_{0}/domepicture_{1}'.format(instance.user.id, filename)
    full_path = os.path.join(settings.MEDIA_ROOT, picture_pic_name)

    if os.path.exists(full_path):
        os.remove(full_path)
    return picture_pic_name


class Dome(models.Model):
    icon = models.ImageField(upload_to=dome_directory_path_picture, null=False)
    banner = models.ImageField(upload_to=dome_directory_path_banner, null=False)
    title = models.CharField(max_length=25, null=False, blank=False)
    description = models.CharField(max_length=144, null=False, blank=False)
    date = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='server_owner')
    members = models.ManyToManyField(User, related_name='dome_members', blank=True)
    moderators = models.ManyToManyField(User, related_name='dome_moderators', blank=True)
    # categories = models.ManyToManyField(Category)
    PRIVACY_CHOICES = ((1,'Public'), (0,'Private'),)
    privacy = models.IntegerField(choices=PRIVACY_CHOICES, default=1)
    invitationstr = models.CharField(default=generate_random, max_length=13, null=False)

    def __str__(self):
        return self.title
    def get_absolute_url(self):
        return reverse('domes:dome-detail', kwargs={'pk':self.pk})
    def get_invitation_link(self):
        slug = slugify(self.title)
        return reverse('domes:dome-invitation', kwargs={'slug': slug,'code':self.invitationstr})
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.icon:
            old = self.icon.path
            img = Image.open(self.icon.path)
            if img.height > 256 and img.width > 256:
                output_size = (256,256)
                img.thumbnail(output_size)
                img.save(self.icon.path)

class Category(models.Model):
    title = models.CharField(max_length=35)
    # text_channels = models.ManyToManyField(TextChannels)
    Dome = models.ForeignKey(Dome,related_name='categories',on_delete=models.CASCADE)

    def __str__(self):
        return self.title


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