import logging
import re

import pusher
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.views import generic
from django.views.decorators.http import require_GET, require_POST

from Domes.access import can_manage_dome, can_participate_in_chat, is_demo_user
from Domes.models import Category
from Domes.ratelimits import UserWriteRateLimitMixin, user_write_rate_limit

from .forms import ChatChannelCreation, ChatMessageCreation
from .models import ChatChannel, ChatMessage


logger = logging.getLogger(__name__)
PRIVATE_CHANNEL_RE = re.compile(r"^private-chat-(?P<channel_id>[1-9][0-9]*)$")


def get_pusher_client():
    values = {
        "app_id": getattr(settings, "PUSHER_APP_ID", ""),
        "key": getattr(settings, "PUSHER_KEY", ""),
        "secret": getattr(settings, "PUSHER_SECRET", ""),
        "cluster": getattr(settings, "PUSHER_CLUSTER", ""),
    }
    if not all(values.values()):
        raise ImproperlyConfigured("Pusher server credentials are not configured.")
    return pusher.Pusher(**values, ssl=True)


def _channel_for_user(user, pk):
    channel = get_object_or_404(
        ChatChannel.objects.select_related("category", "category__Dome", "category__Dome__user"),
        pk=pk,
    )
    if not can_participate_in_chat(user, channel.category.Dome):
        raise PermissionDenied
    return channel


def _publish_message(message):
    try:
        get_pusher_client().trigger(
            f"private-chat-{message.channel_id}",
            "message-created",
            {"message_id": message.pk, "channel_id": message.channel_id},
        )
    except Exception:
        # Persistence is authoritative; a transient realtime outage must not
        # lose the message or expose credentials in the response.
        logger.warning("Unable to publish chat message %s", message.pk)


class ChatMessageList(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    generic.edit.FormMixin,
    generic.ListView,
):
    template_name = "Chat/chat_messages.html"
    model = ChatMessage
    context_object_name = "messages"
    paginate_by = 50
    form_class = ChatMessageCreation
    rate_limit_scope = "chat-message"
    rate_limit_count = 40

    def get_channel(self):
        if not hasattr(self, "channel"):
            self.channel = _channel_for_user(self.request.user, self.kwargs["pk"])
        return self.channel

    def get_queryset(self):
        return (
            ChatMessage.objects.filter(channel=self.get_channel())
            .select_related("user")
            .order_by("date")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        channel = self.get_channel()
        dome = channel.category.Dome
        context.update(
            {
                "channel_id": channel.pk,
                "private_channel_name": f"private-chat-{channel.pk}",
                "pusher_key": getattr(settings, "PUSHER_KEY", ""),
                "pusher_cluster": getattr(settings, "PUSHER_CLUSTER", ""),
                "can_manage_chat": can_manage_dome(self.request.user, dome),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        channel = self.get_channel()
        form = self.get_form()
        if not form.is_valid():
            self.object_list = self.get_queryset()
            return self.render_to_response(
                self.get_context_data(form=form), status=400
            )
        with transaction.atomic():
            message = ChatMessage.objects.create(
                user=request.user,
                body=form.cleaned_data["body"],
                channel=channel,
            )
            transaction.on_commit(lambda: _publish_message(message))
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(status=204)
        return redirect("chat:chat-channel", pk=channel.pk)


class ChatChannelCreateView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.FormView,
):
    template_name = "Chat/chatchannel_form.html"
    form_class = ChatChannelCreation
    rate_limit_scope = "chat-channel-create"
    rate_limit_count = 10

    def get_category(self):
        if not hasattr(self, "category"):
            self.category = get_object_or_404(
                Category.objects.select_related("Dome"), pk=self.kwargs["pk"]
            )
        return self.category

    def test_func(self):
        return can_manage_dome(self.request.user, self.get_category().Dome)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.get_category()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["category"] = self.get_category()
        return kwargs

    def form_valid(self, form):
        channel = form.save(commit=False)
        channel.category = self.get_category()
        channel.save()
        return redirect("domes:dome-detail", pk=channel.category.Dome_id)


@login_required
@require_POST
@user_write_rate_limit("chat-delete", limit=30)
def delete_message(request, pk):
    message = get_object_or_404(
        ChatMessage.objects.select_related(
            "channel", "channel__category", "channel__category__Dome"
        ),
        pk=pk,
    )
    dome = message.channel.category.Dome
    if not can_participate_in_chat(request.user, dome):
        raise PermissionDenied
    can_delete = message.user_id == request.user.pk or (
        not is_demo_user(request.user) and can_manage_dome(request.user, dome)
    )
    if not can_delete:
        raise PermissionDenied
    message.delete()
    return HttpResponse("")


@login_required
@require_POST
@user_write_rate_limit("pusher-auth", limit=120)
def pusher_auth(request):
    channel_name = request.POST.get("channel_name", "")
    socket_id = request.POST.get("socket_id", "")
    match = PRIVATE_CHANNEL_RE.fullmatch(channel_name)
    if not match or not socket_id:
        return HttpResponse("Invalid channel authorization request", status=400)
    _channel_for_user(request.user, int(match.group("channel_id")))
    try:
        authorization = get_pusher_client().authenticate(
            channel=channel_name, socket_id=socket_id
        )
    except ValueError:
        return HttpResponse("Invalid channel authorization request", status=400)
    except ImproperlyConfigured:
        return HttpResponse("Realtime messaging is unavailable", status=503)
    return JsonResponse(authorization)


@login_required
@require_GET
def message_fragment(request, channel_pk, pk):
    message = get_object_or_404(
        ChatMessage.objects.select_related(
            "user", "channel", "channel__category", "channel__category__Dome"
        ),
        pk=pk,
        channel_id=channel_pk,
    )
    dome = message.channel.category.Dome
    if not can_participate_in_chat(request.user, dome):
        raise PermissionDenied
    return TemplateResponse(
        request,
        "Chat/requested_msgs.html",
        {
            "object": message,
            "can_delete": message.user_id == request.user.pk
            or (
                not is_demo_user(request.user)
                and can_manage_dome(request.user, dome)
            ),
        },
    )
