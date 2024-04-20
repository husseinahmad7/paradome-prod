from django.test import TestCase
from django.contrib.auth.models import User
from .models import Message

class TestMessage(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(username='testuser1', password='testpass1')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass2')
        self.message1 = Message.send_message(self.user1, self.user2, 'Hello!')
        self.message2 = Message.send_message(self.user1, self.user2, 'Another message')
        self.message3 = Message.send_message(self.user2, self.user1, 'A reply')

    def test_message_str(self):
        self.assertEqual(str(self.message1), f'{self.user1.username} to: {self.user2.username}')

    def test_message_post_delete(self):
        self.message1.post.delete()
        self.assertFalse(Message.objects.filter(id=self.message1.id).exists())

    def test_message_user_delete(self):
        self.message1.user.delete()
        self.assertFalse(Message.objects.filter(id=self.message1.id).exists())

    def test_message_sender_delete(self):
        self.message1.sender.delete()
        self.assertFalse(Message.objects.filter(id=self.message1.id).exists())

    def test_message_recipient_delete(self):
        self.message1.recipient.delete()
        self.assertFalse(Message.objects.filter(id=self.message1.id).exists())

    def test_message_get_messages(self):
        users = Message.get_messages(self.user1)
        self.assertEqual(len(users), 2)
        self.assertEqual(users[0]['user'], self.user2)
        self.assertEqual(users[1]['user'], self.user1)
        self.assertEqual(users[0]['unread'], 0)
        self.assertEqual(users[1]['unread'], 1)

    def test_message_send_message(self):
        sender_message = Message.send_message(self.user1, self.user2, 'Test message')
        self.assertEqual(sender_message.sender, self.user1)
        self.assertEqual(sender_message.recipient, self.user2)
        self.assertEqual(sender_message.body, 'Test message')
        self.assertTrue(sender_message.is_read)

        recipient_message = Message.objects.get(user=self.user2, sender=self.user1)
        self.assertEqual(recipient_message.sender, self.user1)
        self.assertEqual(recipient_message.recipient, self.user2)
        self.assertEqual(recipient_message.body, 'Test message')
        self.assertFalse(recipient_message.is_read)