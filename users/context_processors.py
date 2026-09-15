from Domes.access import is_demo_user


def demo_session(request):
    """Expose the restricted guest state to shared navigation and page chrome."""
    return {"is_demo_session": is_demo_user(request.user)}
