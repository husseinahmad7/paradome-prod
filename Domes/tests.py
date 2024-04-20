from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Dome, Category

class TestDome(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.dome = Dome.objects.create(
            title='Test Dome',
            description='Test description',
            user=self.user,
            privacy=1,
        )

    def test_dome_str(self):
        self.assertEqual(str(self.dome), 'Test Dome')

    def test_dome_get_absolute_url(self):
        self.assertEqual(self.dome.get_absolute_url(), reverse('domes:dome-detail', kwargs={'pk': self.dome.pk}))

    def test_dome_get_invitation_link(self):
        slug = slugify(self.dome.title)
        self.assertEqual(self.dome.get_invitation_link(), reverse('domes:dome-invitation', kwargs={'slug': slug, 'code': self.dome.invitationstr}))

    def test_dome_picture_upload(self):
        picture_file = open('tests/test_picture.jpg', 'rb')
        self.dome.picture.save('test_picture.jpg', picture_file)
        self.dome.save()
        self.assertTrue(self.dome.picture.name.startswith('user_' + str(self.user.id) + '/'))

    def test_dome_banner_upload(self):
        banner_file = open('tests/test_banner.jpg', 'rb')
        self.dome.banner.save('test_banner.jpg', banner_file)
        self.dome.save()
        self.assertTrue(self.dome.banner.name.startswith('user_' + str(self.user.id) + '/'))

    def test_dome_members(self):
        member = User.objects.create_user(username='member', password='memberpass')
        self.dome.members.add(member)
        self.assertTrue(member in self.dome.members.all())

    def test_dome_moderators(self):
        moderator = User.objects.create_user(username='moderator', password='moderatorpass')
        self.dome.moderators.add(moderator)
        self.assertTrue(moderator in self.dome.moderators.all())

class TestCategory(TestCase):

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

    def test_category_str(self):
        self.assertEqual(str(self.category), 'Test Category')

    def test_category_dome(self):
        self.assertEqual(self.category.Dome, self.dome)