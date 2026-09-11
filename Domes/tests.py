from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .access import (
    can_access_dome,
    can_administer_dome,
    can_manage_dome,
    can_participate_in_chat,
)
from .models import Category, Dome


def make_dome(owner, *, title="Test Dome", privacy=0):
    return Dome.objects.create(
        title=title,
        description="Test description",
        user=owner,
        privacy=privacy,
        icon="",
        banner="",
    )


class DomeAccessPolicyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x")
        self.member = User.objects.create_user("member", password="x")
        self.moderator = User.objects.create_user("moderator", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        self.private = make_dome(self.owner)
        self.private.members.add(self.member)
        self.private.moderators.add(self.moderator)
        self.public = make_dome(self.owner, title="Public Dome", privacy=1)

    def test_public_and_private_visibility(self):
        self.assertTrue(can_access_dome(AnonymousUser(), self.public))
        self.assertFalse(can_access_dome(AnonymousUser(), self.private))
        self.assertTrue(can_access_dome(self.member, self.private))
        self.assertFalse(can_access_dome(self.outsider, self.private))

    def test_management_roles_are_distinct(self):
        self.assertTrue(can_administer_dome(self.owner, self.private))
        self.assertTrue(can_manage_dome(self.moderator, self.private))
        self.assertFalse(can_administer_dome(self.moderator, self.private))
        self.assertFalse(can_manage_dome(self.member, self.private))

    def test_public_chat_still_requires_membership(self):
        self.assertFalse(can_participate_in_chat(self.outsider, self.public))
        self.public.members.add(self.member)
        self.assertTrue(can_participate_in_chat(self.member, self.public))

    def test_demo_dome_is_isolated_from_real_users(self):
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo")
        demo.groups.add(demo_group)
        demo_dome = make_dome(demo, title="Demo Dome")
        demo_dome.members.add(self.member)
        demo_dome.moderators.add(self.moderator)
        self.assertTrue(can_access_dome(demo, demo_dome))
        self.assertFalse(can_access_dome(self.member, demo_dome))
        self.assertFalse(can_manage_dome(self.moderator, demo_dome))
        self.assertFalse(can_manage_dome(demo, demo_dome))


class DomeViewSecurityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="x")
        self.member = User.objects.create_user("member", password="x")
        self.moderator = User.objects.create_user("moderator", password="x")
        self.outsider = User.objects.create_user("outsider", password="x")
        self.dome = make_dome(self.owner)
        self.dome.members.add(self.member)
        self.dome.moderators.add(self.moderator)

    def test_private_dome_detail_filters_out_outsider(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("domes:dome-detail", args=[self.dome.pk]))
        self.assertEqual(response.status_code, 404)

    def test_private_dome_member_can_view(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("domes:dome-detail", args=[self.dome.pk]))
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_create_category(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("domes:category-create", args=[self.dome.pk]),
            {"title": "Restricted"},
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_create_category(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("domes:category-create", args=[self.dome.pk]),
            {"title": "General"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Category.objects.filter(Dome=self.dome, title="General").exists())

    def test_only_owner_can_update_and_delete_dome(self):
        update_url = reverse("domes:dome-update", args=[self.dome.pk])
        delete_url = reverse("domes:dome-delete", args=[self.dome.pk])
        update = {
            "title": "Updated Dome",
            "description": "Updated safely",
            "privacy": "0",
        }
        for user, expected in (
            (self.moderator, 403),
            (self.member, 403),
            (self.outsider, 404),
        ):
            with self.subTest(role=user.username, action="update"):
                self.client.force_login(user)
                self.assertEqual(self.client.post(update_url, update).status_code, expected)
            with self.subTest(role=user.username, action="delete"):
                self.client.force_login(user)
                self.assertEqual(self.client.post(delete_url).status_code, expected)
                self.assertTrue(Dome.objects.filter(pk=self.dome.pk).exists())

        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(update_url, update).status_code, 302)
        self.dome.refresh_from_db()
        self.assertEqual(self.dome.title, "Updated Dome")
        self.assertEqual(self.client.post(delete_url).status_code, 302)
        self.assertFalse(Dome.objects.filter(pk=self.dome.pk).exists())

    def test_moderator_can_create_categories_but_member_and_outsider_cannot(self):
        url = reverse("domes:category-create", args=[self.dome.pk])
        self.client.force_login(self.moderator)
        self.assertEqual(self.client.post(url, {"title": "Moderator"}).status_code, 302)
        for user in (self.member, self.outsider):
            with self.subTest(role=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.post(url, {"title": user.username}).status_code,
                    403,
                )
        self.assertEqual(Category.objects.filter(Dome=self.dome).count(), 1)

    def test_invitation_join_is_idempotent_and_rejects_demo_accounts(self):
        url = self.dome.get_invitation_link()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"join": "invalid"}).status_code, 400)
        self.assertFalse(self.dome.members.filter(pk=self.outsider.pk).exists())
        self.assertEqual(self.client.post(url, {"join": "join"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"join": "join"}).status_code, 302)
        self.assertEqual(self.dome.members.filter(pk=self.outsider.pk).count(), 1)
        for user in (self.owner, self.moderator):
            with self.subTest(existing_role=user.username):
                self.client.force_login(user)
                self.assertEqual(self.client.post(url, {"join": "join"}).status_code, 302)
                self.assertFalse(self.dome.members.filter(pk=user.pk).exists())
        demo_group = Group.objects.create(name="Demo")
        demo = User.objects.create_user("demo")
        demo.groups.add(demo_group)
        self.client.force_login(demo)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_only_owner_can_promote_and_demote_members(self):
        url = reverse(
            "domes:dome-member-raiseordown",
            args=[self.dome.pk, self.member.pk, 1],
        )
        self.client.force_login(self.moderator)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(self.dome.members.filter(pk=self.member.pk).exists())
        self.assertTrue(self.dome.moderators.filter(pk=self.member.pk).exists())
        demote_url = reverse(
            "domes:dome-member-raiseordown",
            args=[self.dome.pk, self.member.pk, 0],
        )
        self.assertEqual(self.client.post(demote_url).status_code, 200)
        self.assertTrue(self.dome.members.filter(pk=self.member.pk).exists())
        self.assertFalse(self.dome.moderators.filter(pk=self.member.pk).exists())
        owner_url = reverse(
            "domes:dome-member-raiseordown",
            args=[self.dome.pk, self.owner.pk, 1],
        )
        self.assertEqual(self.client.post(owner_url).status_code, 403)

    def test_owner_and_moderator_member_removal_matrix(self):
        second_member = User.objects.create_user("second-member", password="x")
        second_moderator = User.objects.create_user("second-moderator", password="x")
        self.dome.members.add(second_member)
        self.dome.moderators.add(second_moderator)
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.post(reverse("domes:dome-member-delete", args=[self.dome.pk, second_member.pk])).status_code,
            403,
        )
        self.client.force_login(self.moderator)
        self.assertEqual(
            self.client.post(reverse("domes:dome-member-delete", args=[self.dome.pk, second_moderator.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("domes:dome-member-delete", args=[self.dome.pk, self.owner.pk])).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("domes:dome-member-delete", args=[self.dome.pk, second_member.pk])).status_code,
            200,
        )
        self.assertFalse(self.dome.members.filter(pk=second_member.pk).exists())
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(reverse("domes:dome-member-delete", args=[self.dome.pk, second_moderator.pk])).status_code,
            200,
        )
        self.assertFalse(self.dome.moderators.filter(pk=second_moderator.pk).exists())

    def test_member_removal_is_post_only(self):
        self.client.force_login(self.owner)
        url = reverse("domes:dome-member-delete", args=[self.dome.pk, self.member.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertFalse(self.dome.members.filter(pk=self.member.pk).exists())

    def test_protected_media_denies_before_storage_access(self):
        self.dome.icon = "private/icon.png"
        self.dome.save(update_fields=["icon"])
        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse("domes:dome-media", args=[self.dome.pk, "icon"])
        )
        self.assertEqual(response.status_code, 403)

    def test_category_database_constraint(self):
        Category.objects.create(Dome=self.dome, title="General")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Category.objects.create(Dome=self.dome, title="General")
