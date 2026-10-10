from django.conf import settings


def engineering_lab(request):
    return {
        "engineering_lab_enabled": settings.ENGINEERING_LAB_ENABLED,
        "engineering_control_room_enabled": settings.ENGINEERING_CONTROL_ROOM_ENABLED,
    }
