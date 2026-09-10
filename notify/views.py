from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from Domes.access import is_demo_user
from Domes.ratelimits import user_write_rate_limit

from .models import Notification


@login_required
def showNotification(request):
    if is_demo_user(request.user):
        raise PermissionDenied
    notifications = Notification.objects.filter(user=request.user).order_by("-date")
    return render(
        request,
        "notify/notifications.html",
        {"notifications": notifications},
    )


@login_required
@require_POST
@user_write_rate_limit("notification-delete", limit=60)
def deleteNotification(request, notify_pk):
    if is_demo_user(request.user):
        raise PermissionDenied
    notification = get_object_or_404(
        Notification, pk=notify_pk, user=request.user
    )
    notification.delete()
    return redirect("notify:notification")


def CountNotifications(request):
    notify_count = 0
    if request.user.is_authenticated and not is_demo_user(request.user):
        notify_count = Notification.objects.filter(
            user=request.user, is_seen=False
        ).count()
    return {"notify_count": notify_count}
