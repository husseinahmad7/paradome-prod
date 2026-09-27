"""Regression evidence for pure, object, queryset and explorer policy parity."""

from dataclasses import asdict
from itertools import product

from django.contrib.auth.models import AnonymousUser, Group, User
from django.http import QueryDict
from django.test import SimpleTestCase, TestCase

from Domes.access import (
    DomePolicyFacts,
    accessible_domes,
    can_access_dome,
    can_administer_dome,
    can_create_dome_content,
    can_manage_dome,
    can_participate_in_chat,
    dome_access_q,
    evaluate_dome_policy,
)
from Domes.models import Category, Dome

from .permissions import ACTIONS, RESOURCES, ROLES, permission_explorer


OBJECT_CHECKS = {
    "access": can_access_dome,
    "manage": can_manage_dome,
    "administer": can_administer_dome,
    "create_content": can_create_dome_content,
    "participate_chat": can_participate_in_chat,
}
PARTICIPANT = {"access", "participate_chat"}
MODERATOR = PARTICIPANT | {"manage", "create_content"}
OWNER = MODERATOR | {"administer"}
DEMO_OWNER = PARTICIPANT | {"create_content"}


class PureDomePolicyTests(SimpleTestCase):
    def test_complete_boolean_matrix_matches_legacy_rules_without_database(self):
        """All 128 fact combinations, including invalid identity combinations."""

        for values in product((False, True), repeat=7):
            facts = DomePolicyFacts(*values)
            with self.subTest(facts=facts):
                authenticated = facts.authenticated
                owner = authenticated and facts.owner
                member = authenticated and facts.member
                moderator = authenticated and facts.moderator
                if authenticated and facts.demo_user:
                    expected = {
                        "access": owner,
                        "manage": False,
                        "administer": False,
                        "create_content": owner,
                        "participate_chat": owner,
                    }
                else:
                    expected = {
                        "access": not facts.demo_owned
                        and (facts.public or owner or member or moderator),
                        "manage": not facts.demo_owned and (owner or moderator),
                        "administer": owner,
                        "create_content": not facts.demo_owned and (owner or moderator),
                        "participate_chat": not facts.demo_owned
                        and (owner or member or moderator),
                    }
                self.assertEqual(asdict(evaluate_dome_policy(facts)), expected)

    def test_explorer_has_complete_fixed_role_resource_matrix(self):
        normal_private = {
            "anonymous": set(),
            "outsider": set(),
            "member": PARTICIPANT,
            "moderator": MODERATOR,
            "owner": OWNER,
            "demo": set(),
        }
        for role, _ in ROLES:
            for resource, _, _ in RESOURCES:
                with self.subTest(role=role, resource=resource):
                    context = permission_explorer(QueryDict(f"role={role}&resource={resource}"))
                    if resource in {"demo", "other-demo"}:
                        expected = DEMO_OWNER if role == "demo" and resource == "demo" else set()
                    else:
                        expected = normal_private[role]
                        if resource == "public" and role != "demo":
                            expected = expected | {"access"}
                    actual = {row["action"] for row in context["decisions"] if row["allowed"]}
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(context["decisions"]), len(ACTIONS))
                    self.assertTrue(all(row["explanation"] for row in context["decisions"]))

    def test_explorer_never_echoes_unrecognized_inputs_or_accepts_ids(self):
        untrusted = "<script>untrusted</script>"
        context = permission_explorer({
            "role": untrusted,
            "resource": untrusted,
            "user_id": "1",
            "dome_id": "1",
        })
        self.assertEqual(context["selected_role"], "anonymous")
        self.assertEqual(context["selected_resource"], "private")
        self.assertNotIn(untrusted, str(context))
        self.assertFalse(any(row["allowed"] for row in context["decisions"]))

    def test_explorer_defaults_to_safe_private_anonymous_scenario(self):
        context = permission_explorer(QueryDict())
        self.assertEqual(context["selected_role"], "anonymous")
        self.assertEqual(context["selected_resource"], "private")
        self.assertIn("never changed or inspected", context["simulation_notice"])


class DomePolicyParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {
            role: User.objects.create_user(username=f"lab-policy-{role}")
            for role in ("outsider", "member", "moderator", "owner", "demo", "other-demo")
        }
        demo_group = Group.objects.create(name="Demo")
        cls.users["demo"].groups.add(demo_group)
        cls.users["other-demo"].groups.add(demo_group)
        cls.domes = {}
        for name, owner_role, privacy in (
            ("private", "owner", 0),
            ("public", "owner", 1),
            ("demo-private", "demo", 0),
            ("demo-public", "demo", 1),
            ("other-demo-private", "other-demo", 0),
            ("other-demo-public", "other-demo", 1),
        ):
            dome = Dome.objects.create(
                title=f"Lab {name}",
                description="Permission parity fixture",
                user=cls.users[owner_role],
                privacy=privacy,
                icon="",
                banner="",
            )
            # Test exclusion even when accidental membership records exist.
            dome.members.add(cls.users["member"], cls.users["demo"])
            dome.moderators.add(cls.users["moderator"], cls.users["other-demo"])
            Category.objects.create(Dome=dome, title="Parity")
            cls.domes[name] = dome

    def _facts(self, user, dome):
        authenticated = bool(user and user.is_authenticated)
        user_id = user.pk if authenticated else None
        return DomePolicyFacts(
            authenticated=authenticated,
            demo_user=authenticated and user.groups.filter(name="Demo").exists(),
            demo_owned=dome.user.groups.filter(name="Demo").exists(),
            public=dome.privacy == 1,
            owner=authenticated and dome.user_id == user_id,
            member=authenticated and dome.members.filter(pk=user_id).exists(),
            moderator=authenticated and dome.moderators.filter(pk=user_id).exists(),
        )

    def _expected_actions(self, role, name):
        if role in {"demo", "other-demo"}:
            owner_role = "other-demo" if name.startswith("other-demo") else "demo"
            return DEMO_OWNER if "demo" in name and role == owner_role else set()
        if "demo" in name:
            return set()
        private_actions = {
            "anonymous": set(),
            "none": set(),
            "outsider": set(),
            "member": PARTICIPANT,
            "moderator": MODERATOR,
            "owner": OWNER,
        }
        result = private_actions[role]
        return result | {"access"} if name == "public" else result

    def test_full_object_and_pure_policy_matrix_preserves_expected_permissions(self):
        users = {"anonymous": AnonymousUser(), "none": None, **self.users}
        for role, user in users.items():
            for name, dome in self.domes.items():
                with self.subTest(role=role, resource=name):
                    expected = self._expected_actions(role, name)
                    pure = asdict(evaluate_dome_policy(self._facts(user, dome)))
                    actual = {action: check(user, dome) for action, check in OBJECT_CHECKS.items()}
                    self.assertEqual({action for action, allowed in actual.items() if allowed}, expected)
                    self.assertEqual(actual, pure)

    def test_queryset_object_and_related_queryset_visibility_are_identical(self):
        users = {"anonymous": AnonymousUser(), "none": None, **self.users}
        for role, user in users.items():
            with self.subTest(role=role):
                expected = {
                    dome.pk for name, dome in self.domes.items()
                    if "access" in self._expected_actions(role, name)
                }
                self.assertSetEqual(set(accessible_domes(user).values_list("pk", flat=True)), expected)
                self.assertSetEqual(
                    set(Dome.objects.filter(dome_access_q(user)).values_list("pk", flat=True)),
                    expected,
                )
                self.assertSetEqual(
                    set(Category.objects.filter(dome_access_q(user, "Dome__")).values_list("Dome_id", flat=True)),
                    expected,
                )

    def test_member_moderator_overlap_does_not_drop_moderation(self):
        dome = self.domes["private"]
        user = self.users["member"]
        dome.moderators.add(user)
        actual = {action for action, check in OBJECT_CHECKS.items() if check(user, dome)}
        self.assertSetEqual(actual, MODERATOR)

    def test_explorer_cannot_change_real_account_or_memberships(self):
        user = self.users["outsider"]
        group_ids = list(user.groups.values_list("pk", flat=True))
        memberships = list(user.dome_members.values_list("pk", flat=True))
        with self.assertNumQueries(0):
            permission_explorer(QueryDict(f"role=owner&resource=private&user_id={user.pk}"))
        self.assertEqual(list(user.groups.values_list("pk", flat=True)), group_ids)
        self.assertEqual(list(user.dome_members.values_list("pk", flat=True)), memberships)

    def test_public_read_does_not_add_membership_queries(self):
        user = self.users["outsider"]
        dome = Dome.objects.select_related("user").get(pk=self.domes["public"].pk)
        with self.assertNumQueries(2):
            self.assertTrue(can_access_dome(user, dome))
