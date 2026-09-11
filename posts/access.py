"""Authorization helpers for Post and Comment resources."""

from django.db.models import Q

from Domes.access import (
    DEMO_GROUP_NAME,
    can_access_dome,
    can_manage_dome,
    dome_access_q,
    is_demo_user,
)

from .models import Post


def accessible_posts(user, queryset=None):
    queryset = queryset if queryset is not None else Post.objects.all()
    if is_demo_user(user):
        return queryset.filter(dome__user_id=user.pk).distinct()
    return queryset.filter(
        (
            Q(dome__isnull=True)
            & ~Q(user__groups__name=DEMO_GROUP_NAME)
        )
        | dome_access_q(user, "dome__")
    ).distinct()


def can_access_post(user, post):
    if is_demo_user(user):
        return post.dome_id is not None and post.dome.user_id == user.pk
    if post.user.groups.filter(name=DEMO_GROUP_NAME).exists():
        return False
    return post.dome_id is None or can_access_dome(user, post.dome)


def can_moderate_post(user, post):
    if not getattr(user, "is_authenticated", False) or is_demo_user(user):
        return False
    return post.user_id == user.pk or (
        post.dome_id is not None and can_manage_dome(user, post.dome)
    )
