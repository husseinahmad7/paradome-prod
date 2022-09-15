from django.db import models
import datetime
from django.utils import timezone
from django.contrib import admin
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify
from django.db.models.signals import post_save
from Domes.models import Dome
from ckeditor.fields import RichTextField
from django.core.exceptions import ValidationError

def user_directory_path(instance,filename):
     return f'posts/{filename}'

def validate_image(fieldfile_obj):
    filesize = fieldfile_obj.file.size
    megabyte_limit = 4.0
    if filesize > megabyte_limit*1024*1024:
        raise ValidationError("Max file size is %sMB" % str(megabyte_limit))
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
    content = RichTextField(config_name='default')
    # content = models.TextField(max_length=2000)
    picture = models.ImageField(upload_to=user_directory_path,null=True, blank=True, validators=[validate_image])
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
    @property
    def comment_count(self):
        return Comment.objects.filter(post=self).count()
    


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='comments', on_delete=models.CASCADE)
    comment = RichTextField(config_name='comment')
    commented = models.DateTimeField(auto_now_add=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, related_name='replied_to', on_delete=models.CASCADE)
    
    #approved boolean def approved(self): self.approved = True self.save()
    def __str__(self):
        return f"{self.post.question_text} -- {self.comment[:20]} -- by {self.user}"
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

class Stream(models.Model):
    following = models.ForeignKey(User, on_delete=models.CASCADE, related_name="stream_following")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    date = models.DateTimeField()
    
    def add_post(sender, instance, *args, **kwargs):
        post= instance
        
        if post.dome is not None and post.dome.privacy == 0:
            return
        else:
            user = post.user
            followers = Follow.objects.all().filter(following=user)
            for follower in followers:
                stream = Stream(post=post, user=follower.follower , following= user, date=post.posted_date)
                stream.save()
            
class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_likes")
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='post_likes')
    
post_save.connect(Stream.add_post,sender=Post) #registering the signal handler