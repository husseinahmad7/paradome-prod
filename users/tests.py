import os
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from .models import Profile

class TestProfile(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.profile = Profile.objects.create(user=self.user)

    def test_profile_str(self):
        self.assertEqual(str(self.profile), 'testuser Profile')

    def test_profile_picture_default(self):
        self.assertEqual(self.profile.picture.name, 'profile_pics/default.jpg')

    def test_profile_picture_upload(self):
        image_file = SimpleUploadedFile('test.jpg', content=b'test_content')
        self.profile.picture = image_file
        self.profile.save()
        self.assertEqual(self.profile.picture.name, 'profile_pics/user_1.jpg')

    def test_profile_picture_resize(self):
        image_file = SimpleUploadedFile('large_test.jpg', content=b'large_test_content')
        self.profile.picture = image_file
        self.profile.save()
        self.assertEqual(self.profile.picture.height, 300)
        self.assertEqual(self.profile.picture.width, 300)

    def test_profile_picture_delete(self):
        image_file = SimpleUploadedFile('test.jpg', content=b'test_content')
        self.profile.picture = image_file
        self.profile.save()
        self.profile.picture = None
        self.profile.save()
        self.assertFalse(os.path.exists(self.profile.picture.path))