"""Central authorization policy for Dome-owned resources.

Keep permission decisions here so nested resources (posts, categories and chat
channels) cannot accidentally bypass the parent Dome's privacy boundary.
"""

from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import Dome


DEMO_GROUP_NAME = "Demo"


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
    if is_demo_user(user):
        return dome.user_id == user.pk
    if is_demo_owned_dome(dome):
        return False
    if dome.privacy == 1:
        return True

    user_id = _authenticated_user_id(user)
    if user_id is None:
        return False
    if dome.user_id == user_id:
        return True
    return dome.members.filter(pk=user_id).exists() or dome.moderators.filter(
        pk=user_id
    ).exists()


def can_manage_dome(user, dome):
    """Owners and moderators may create and moderate Dome content."""

    if is_demo_user(user) or is_demo_owned_dome(dome):
        return False
    user_id = _authenticated_user_id(user)
    if user_id is None:
        return False
    return dome.user_id == user_id or dome.moderators.filter(pk=user_id).exists()


def can_administer_dome(user, dome):
    """Only the owner may change membership roles or Dome settings."""

    if is_demo_user(user):
        return False
    user_id = _authenticated_user_id(user)
    return user_id is not None and dome.user_id == user_id


def can_create_dome_content(user, dome):
    if is_demo_user(user):
        return dome.user_id == user.pk
    return can_manage_dome(user, dome)


def can_participate_in_chat(user, dome):
    """Chat is private to explicit Dome participants, including public Domes."""

    user_id = _authenticated_user_id(user)
    if user_id is None:
        return False
    if is_demo_user(user):
        return dome.user_id == user_id
    if is_demo_owned_dome(dome):
        return False
    return (
        dome.user_id == user_id
        or dome.members.filter(pk=user_id).exists()
        or dome.moderators.filter(pk=user_id).exists()
    )


def require_dome_access(user, dome):
    if not can_access_dome(user, dome):
        raise PermissionDenied
    return dome


def require_dome_management(user, dome):
    if not can_manage_dome(user, dome):
        raise PermissionDenied
    return dome
