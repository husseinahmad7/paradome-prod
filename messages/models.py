from django.db import models
from django.contrib.auth.models import User
from django.db.models import Max

class Message(models.Model):
    user = models.ForeignKey(User, related_name='user', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='from_user', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='to_user', on_delete=models.CASCADE)
    body = models.TextField(max_length=1000,blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    def __str__(self):
        return f'{self.sender.username} to: {self.recipient.username}'
    
    def send_message(from_user, to_user, body):
        sender_message = Message(user=from_user ,sender=from_user ,recipient=to_user ,body=body , is_read=True)
        sender_message.save()
        recipient_message = Message(user=to_user,sender=from_user ,recipient=from_user ,body=body)
        recipient_message.save()
        return sender_message
    
    def get_messages(user):
        users = []
        messages = Message.objects.filter(user=user).values('recipient').annotate(last=Max('date')).order_by('-last')
        
        for message in messages:
            users.append({'user': User.objects.get(pk=message['recipient']),
                          'last': message['last'],
                          'unread': Message.objects.filter(user=user, recipient__pk=message['recipient'], is_read=False).count()})
        return users