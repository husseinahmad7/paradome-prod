from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Notification

class TestNotification(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.notification = Notification.objects.create(user=self.user, sender=self.user, notification_type=1)

    def test_notification_str(self):
        self.assertEqual(str(self.notification), f'{self.user.username} received a like notification')

    def test_notification_absolute_url(self):
        self.assertEqual(self.notification.get_absolute_url(), '/posts/1/')

    def test_notification_post_delete(self):
        self.notification.post.delete()
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_notification_user_delete(self):
        self.notification.user.delete()
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_notification_sender_delete(self):
        self.notification.sender.delete()
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_notification_delete_if_seen(self):
        self.notification.is_seen = True
        self.notification.save()
        self.notification.delete()
        self.assertFalse(Notification.objects.filter(id=self.notification.id).exists())

    def test_notification_delete_if_not_seen(self):
        self.notification.is_seen = False
        self.notification.save()
        self.notification.delete()
        self.assertTrue(Notification.objects.filter(id=self.notification.id).exists())