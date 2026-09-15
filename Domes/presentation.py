from .access import (
    can_administer_dome,
    can_manage_dome,
    can_participate_in_chat,
    is_demo_owned_dome,
    is_demo_user,
)


def dome_shell_context(user, dome, *, active_section="overview", active_channel_id=None):
    """Return the shared context required by the complete Dome workspace shell."""

    return {
        "object": dome,
        "dome": dome,
        "can_administer": can_administer_dome(user, dome),
        "can_manage": can_manage_dome(user, dome),
        "can_chat": can_participate_in_chat(user, dome),
        "can_direct_message": (
            user.is_authenticated
            and not is_demo_user(user)
            and not is_demo_owned_dome(dome)
            and user != dome.user
        ),
        "active_section": active_section,
        "active_channel_id": active_channel_id,
    }
