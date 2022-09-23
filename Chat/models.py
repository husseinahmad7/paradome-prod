from django.db import models
from django.contrib.auth.models import User
from Domes.models import Category

# Create your models here.
def user_directory_path(instance, filename):
    #This file will be uploadded to MEDIA /user_(id)/the file
    return 'chat_{0}/{1}'.format(instance.channel.id, filename)


class ChatChannel(models.Model):
    title = models.CharField(max_length=25)
    topic = models.CharField(max_length=50)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='chat_chnls')
    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField(max_length=1500, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    # file = models.FileField(upload_to=user_directory_path, blank=True, null=True)
    channel = models.ForeignKey(ChatChannel, on_delete=models.CASCADE, related_name='chat_msg')
    is_read = models.BooleanField(default=False)