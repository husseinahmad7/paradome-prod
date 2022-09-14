from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse

class Notification(models.Model):
    NOTIFICATION_TYPE = ((1,'like'), (2,'comment'), (3,'follow'))
    
    post = models.ForeignKey('posts.Post',on_delete=models.CASCADE, related_name='noti_post', blank=True, null=True)
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='noti_from_user')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='noti_to_user')
    notification_type = models.IntegerField(choices=NOTIFICATION_TYPE)
    text_preview = models.CharField(max_length=350, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    is_seen = models.BooleanField(default=False)
    
    def get_absolute_url(self):
        if self.notification_type == 1 or self.notification_type == 2:
            return reverse('posts:post-detail', kwargs={'pk': self.post.pk})
        elif self.notification_type == 3:
            return reverse("posts:user-posts", kwargs={"username": self.sender.username})
    