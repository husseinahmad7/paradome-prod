from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from Domes.access import is_demo_user
from Domes.ratelimits import user_write_rate_limit

from .forms import DirectMessageForm
from .models import Message


def _ensure_direct_messages_allowed(user):
    if is_demo_user(user):
        raise PermissionDenied


def _inbox_context(user, active_user=None, form=None):
    conversations = Message.get_messages(user=user)
    if active_user is None and conversations:
        active_user = conversations[0]["user"]
    directs = Message.objects.none()
    if active_user is not None:
        directs = (
            Message.objects.filter(user=user, recipient=active_user)
            .select_related("sender")
            .order_by("date")
        )
    return {
        "directs": directs,
        "messages": conversations,
        "active_direct": active_user.username if active_user else None,
        "form": form or DirectMessageForm(),
    }


@login_required
def inbox(request):
    _ensure_direct_messages_allowed(request.user)
    return render(request, "messages/inbox.html", _inbox_context(request.user))


@login_required
@require_http_methods(["GET", "POST"])
@user_write_rate_limit("direct-message", limit=20)
def directs(request, username):
    _ensure_direct_messages_allowed(request.user)
    active_user = get_object_or_404(
        User.objects.exclude(groups__name="Demo"), username=username
    )
    if active_user == request.user:
        raise PermissionDenied
    if request.method == "POST":
        form = DirectMessageForm(request.POST)
        if form.is_valid():
            Message.send_message(
                from_user=request.user,
                to_user=active_user,
                body=form.cleaned_data["body"],
            )
            return redirect("messages:directs", username=active_user.username)
        return render(
            request,
            "messages/inbox.html",
            _inbox_context(request.user, active_user, form),
            status=400,
        )
    return render(
        request,
        "messages/inbox.html",
        _inbox_context(request.user, active_user),
    )


@login_required
@require_POST
@user_write_rate_limit("direct-message-read", limit=60)
def mark_directs_read(request, username):
    _ensure_direct_messages_allowed(request.user)
    active_user = get_object_or_404(
        User.objects.exclude(groups__name="Demo"), username=username
    )
    if active_user == request.user:
        raise PermissionDenied
    Message.objects.filter(
        user=request.user,
        recipient=active_user,
        is_read=False,
    ).update(is_read=True)
    if request.headers.get("HX-Request") == "true":
        return HttpResponse(status=204)
    return redirect("messages:directs", username=active_user.username)


def check_directs(request):
    unread_count = 0
    if request.user.is_authenticated and not is_demo_user(request.user):
        unread_count = Message.objects.filter(
            user=request.user, is_read=False
        ).count()
    return {"unread_count": unread_count}
