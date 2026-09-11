from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q

from Domes.access import is_demo_user

class Message(models.Model):
    user = models.ForeignKey(User, related_name='user', on_delete=models.CASCADE)
    sender = models.ForeignKey(User, related_name='from_user', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='to_user', on_delete=models.CASCADE)
    body = models.TextField(max_length=1000)
    date = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    def __str__(self):
        return f'{self.sender.username} to: {self.recipient.username}'
    
    @staticmethod
    def send_message(from_user, to_user, body):
        body = (body or "").strip()
        if not body:
            raise ValidationError("Message cannot be empty.")
        if from_user == to_user:
            raise ValidationError("You cannot message yourself.")
        if is_demo_user(from_user) or is_demo_user(to_user):
            raise ValidationError("Demo accounts cannot use direct messages.")
        with transaction.atomic():
            sender_message = Message.objects.create(
                user=from_user,
                sender=from_user,
                recipient=to_user,
                body=body,
                is_read=True,
            )
            Message.objects.create(
                user=to_user,
                sender=from_user,
                recipient=from_user,
                body=body,
            )
        return sender_message
    
    @staticmethod
    def get_messages(user):
        summaries = list(
            Message.objects.filter(user=user).exclude(recipient__groups__name="Demo")
            .values("recipient")
            .annotate(
                last=Max("date"),
                unread=Count("id", filter=Q(is_read=False)),
            )
            .order_by("-last")
        )
        recipients = User.objects.in_bulk(
            summary["recipient"] for summary in summaries
        )
        return [
            {
                "user": recipients[summary["recipient"]],
                "last": summary["last"],
                "unread": summary["unread"],
            }
            for summary in summaries
            if summary["recipient"] in recipients
        ]

    class Meta:
        indexes = [
            models.Index(fields=["user", "recipient", "-date"], name="dm_conversation_idx"),
            models.Index(fields=["user", "is_read"], name="dm_unread_idx"),
        ]
