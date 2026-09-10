from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class PrivateProfileFormTests(TestCase):
    def test_form_renders_without_requesting_a_public_media_url(self):
        user = User.objects.create_user("profile-form", password="x")
        self.client.force_login(user)

        response = self.client.get(reverse("users:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="file"')
