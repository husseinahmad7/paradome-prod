from django.conf import settings


def engineering_lab(request):
    return {"engineering_lab_enabled": settings.ENGINEERING_LAB_ENABLED}
