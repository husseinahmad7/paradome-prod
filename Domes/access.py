"""Central authorization policy for Dome-owned resources.

Keep permission decisions here so nested resources (posts, categories and chat
channels) cannot accidentally bypass the parent Dome's privacy boundary.
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Dome


DEMO_GROUP_NAME = "Demo"


@dataclass(frozen=True)
class DomePolicyFacts:
    """Identity-free inputs to the Dome policy, also usable by simulations."""

    authenticated: bool = False
    demo_user: bool = False
    demo_owned: bool = False
    public: bool = False
    owner: bool = False
    member: bool = False
    moderator: bool = False


@dataclass(frozen=True)
class DomePolicyDecision:
    access: bool
    manage: bool
    administer: bool
    create_content: bool
    participate_chat: bool


def evaluate_dome_policy(facts: DomePolicyFacts) -> DomePolicyDecision:
    """Evaluate permissions without users, database reads, or side effects.

    Public visibility does not imply permission to post or join a chat. Demo
    identities are an earlier, separate boundary: they may use their own Dome
    but cannot administer or moderate it, or interact with any other Dome.
    """

    owner = facts.authenticated and facts.owner
    member = facts.authenticated and facts.member
    moderator = facts.authenticated and facts.moderator
    if facts.authenticated and facts.demo_user:
        return DomePolicyDecision(
            access=owner,
            manage=False,
            administer=False,
            create_content=owner,
            participate_chat=owner,
        )

    manage = not facts.demo_owned and (owner or moderator)
    return DomePolicyDecision(
        access=not facts.demo_owned and (facts.public or owner or member or moderator),
        manage=manage,
        # Ownership implies a non-demo-owned resource for a real account. Keep
        # this owner-only rule identical to the existing object policy.
        administer=owner,
        create_content=manage,
        participate_chat=not facts.demo_owned and (owner or member or moderator),
    )


def _decide_dome_action(user, dome, action):
    """Load only facts relevant to one action, then use the pure evaluator.

    Membership queries are unnecessary when ownership, demo isolation, or
    public-read access has already settled the requested action. Omitted
    relationship facts therefore cannot affect the returned decision.
    """

    user_id = _authenticated_user_id(user)
    authenticated = user_id is not None
    owner = authenticated and dome.user_id == user_id
    demo_user = is_demo_user(user)
    public = dome.privacy == 1
    demo_owned = (
        action != "administer"
        and (authenticated or action == "access")
        and not demo_user
        and is_demo_owned_dome(dome)
    )
    member = moderator = False
    needs_relationships = authenticated and not (owner or demo_user or demo_owned)
    if needs_relationships:
        if action == "participate_chat" or (action == "access" and not public):
            member = dome.members.filter(pk=user_id).exists()
            if not member:
                moderator = dome.moderators.filter(pk=user_id).exists()
        elif action in {"manage", "create_content"}:
            moderator = dome.moderators.filter(pk=user_id).exists()

    decision = evaluate_dome_policy(
        DomePolicyFacts(
            authenticated=authenticated,
            demo_user=demo_user,
            demo_owned=demo_owned,
            public=public,
            owner=owner,
            member=member,
            moderator=moderator,
        )
    )
    return getattr(decision, action)


def _authenticated_user_id(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user.pk


def is_demo_user(user):
    user_id = _authenticated_user_id(user)
    return user_id is not None and user.groups.filter(name=DEMO_GROUP_NAME).exists()


def is_demo_owned_dome(dome):
    return dome.user.groups.filter(name=DEMO_GROUP_NAME).exists()


def dome_access_q(user, prefix=""):
    """Return a Q expression for Domes visible to user.

    prefix allows the policy to be applied through a relation, for example
    dome_access_q(user, "dome__") for posts.
    """

    user_id = _authenticated_user_id(user)
    if user_id is None:
        return Q(**{f"{prefix}privacy": 1}) & ~Q(
            **{f"{prefix}user__groups__name": DEMO_GROUP_NAME}
        )
    if is_demo_user(user):
        return Q(**{f"{prefix}user_id": user_id})

    visible = (
        (
            Q(**{f"{prefix}privacy": 1})
        )
        | Q(**{f"{prefix}user_id": user_id})
        | Q(**{f"{prefix}members__id": user_id})
        | Q(**{f"{prefix}moderators__id": user_id})
    )
    # Demo sandboxes stay isolated even if a real account is accidentally
    # present in their membership tables.
    return visible & ~Q(**{f"{prefix}user__groups__name": DEMO_GROUP_NAME})


def accessible_domes(user, queryset=None):
    queryset = queryset if queryset is not None else Dome.objects.all()
    return queryset.filter(dome_access_q(user)).distinct()


def can_access_dome(user, dome):
    return _decide_dome_action(user, dome, "access")


def can_manage_dome(user, dome):
    """Owners and moderators may create and moderate Dome content."""

    return _decide_dome_action(user, dome, "manage")


def can_administer_dome(user, dome):
    """Only the owner may change membership roles or Dome settings."""

    return _decide_dome_action(user, dome, "administer")


def can_create_dome_content(user, dome):
    return _decide_dome_action(user, dome, "create_content")


def can_participate_in_chat(user, dome):
    """Chat is private to explicit Dome participants, including public Domes."""

    return _decide_dome_action(user, dome, "participate_chat")


def require_dome_access(user, dome):
    if not can_access_dome(user, dome):
        raise PermissionDenied
    return dome


def require_dome_management(user, dome):
    if not can_manage_dome(user, dome):
        raise PermissionDenied
    return dome
