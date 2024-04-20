from django.test import TestCase
from django.contrib.auth.models import User
from Domes.models import Dome, Category, ChatChannel, ChatMessage

class TestChatChannel(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.dome = Dome.objects.create(
            title='Test Dome',
            description='Test description',
            user=self.user,
            privacy=1,
        )
        self.category = Category.objects.create(
            title='Test Category',
            Dome=self.dome,
        )
        self.chat_channel = ChatChannel.objects.create(
            title='Test Chat Channel',
            topic='Test Topic',
            category=self.category,
        )

    def test_chat_channel_str(self):
        self.assertEqual(str(self.chat_channel), 'Test Chat Channel')

    def test_chat_channel_category(self):
        self.assertEqual(self.chat_channel.category, self.category)


class TestChatMessage(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.dome = Dome.objects.create(
            title='Test Dome',
            description='Test description',
            user=self.user,
            privacy=1,
        )
        self.category = Category.objects.create(
            title='Test Category',
            Dome=self.dome,
        )
        self.chat_channel = ChatChannel.objects.create(
            title='Test Chat Channel',
            topic='Test Topic',
            category=self.category,
        )
        self.chat_message = ChatMessage.objects.create(
            user=self.user,
            body='Test message',
            channel=self.chat_channel,
        )

    def test_chat_message_str(self):
        self.assertEqual(str(self.chat_message), 'Test message')

    def test_chat_message_user(self):
        self.assertEqual(self.chat_message.user, self.user)

    def test_chat_message_channel(self):
        self.assertEqual(self.chat_message.channel, self.chat_channel)

    def test_chat_message_is_read(self):
        self.assertEqual(self.chat_message.is_read, False)