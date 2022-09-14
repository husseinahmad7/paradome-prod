from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from posts.models import Like, Follow, Comment
from notify.models import Notification

@receiver(post_save, sender=Like)
def user_liked_post(sender, instance, **kwargs):
    like = instance
    post = like.post
    sender = like.user
    notify = Notification(post=post, sender=sender, user=post.user, notification_type=1, text_preview=f'liked your post "{post.question_text}"')
    notify.save()

@receiver(post_delete, sender=Like)
def user_disliked_post(sender, instance, **kwargs):
    like = instance
    post = like.post
    sender = like.user
    notify = Notification.objects.filter(post=post, sender=sender, user=post.user, notification_type=1)
    notify.delete()
    
@receiver(post_save, sender=Follow)
def user_follow(sender, instance, **kwargs):
    follow = instance
    following = follow.following
    sender = follow.follower
    
    notify = Notification(sender=sender, user=following, notification_type=3, text_preview='is following you')
    notify.save()
    
@receiver(post_delete, sender=Follow)
def user_unfollow(sender, instance, **kwargs):
    follow = instance
    following = follow.following
    sender = follow.follower
    
    notify = Notification.objects.filter(sender=sender, user=following, notification_type=3)
    notify.delete()

@receiver(post_save, sender=Comment)
def comment_add(sender, instance, **kwargs):
    comment = instance
    post = comment.post
    sender = comment.user
    text_preview = comment.comment[:89]
    
    notify = Notification(post=post, sender=sender, user=post.user, notification_type=2, text_preview=f'commented on your post "{post.question_text}": {text_preview}')
    notify.save()

@receiver(post_delete, sender=Comment)
def comment_delete(sender, instance, **kwargs):
    comment = instance
    post = comment.post
    sender = comment.user
    text_preview = comment.comment[:89]
    
    notify = Notification.objects.filter(post=post, sender=sender, user=post.user, notification_type=2, text_preview=f'commented on your post "{post.question_text}": {text_preview}')
    notify.delete()