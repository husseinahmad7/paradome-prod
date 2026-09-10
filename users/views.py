from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from Domes.access import is_demo_user
from Domes.models import Dome
from Domes.ratelimits import AnonymousWriteRateLimitMixin, rate_limit
from Domes.storage import open_validated_image, safe_image_filename

from .forms import ProfileUpdateForm, UserRegisterForm, UserUpdateForm


class RateLimitedLoginView(AnonymousWriteRateLimitMixin, auth_views.LoginView):
    template_name = "users/login.html"
    rate_limit_scope = "login"
    rate_limit_count = 8
    rate_limit_window_seconds = 300


class RateLimitedPasswordResetView(
    AnonymousWriteRateLimitMixin, auth_views.PasswordResetView
):
    template_name = "users/password_reset.html"
    rate_limit_scope = "password-reset"
    rate_limit_count = 5
    rate_limit_window_seconds = 900


def index(request):
    if not request.user.is_authenticated:
        return redirect("users:login")
    if is_demo_user(request.user):
        dome = Dome.objects.filter(user=request.user).first()
        if dome:
            return redirect("domes:dome-detail", pk=dome.pk)
    return render(request, "users/user.html", {"title": request.user.username})


@rate_limit("registration", limit=5, window_seconds=3600)
def register_view(request):
    if request.user.is_authenticated:
        return redirect("users:index")
    form = UserRegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your account has been created. You can now sign in.")
        return redirect("users:login")
    return render(request, "users/register.html", {"form": form})


@require_POST
@rate_limit("demo-login", limit=20, window_seconds=300)
def demo_login(request):
    from django.conf import settings

    if not getattr(settings, "DEMO_ACCOUNT_ENABLED", False):
        return HttpResponse("The demo sandbox is temporarily unavailable.", status=503)
    username = getattr(settings, "DEMO_USERNAME", "")
    demo_user = User.objects.filter(username=username, is_active=True).first()
    if (
        not demo_user
        or not is_demo_user(demo_user)
        or demo_user.has_usable_password()
    ):
        return HttpResponse("The demo sandbox is temporarily unavailable.", status=503)
    dome = Dome.objects.filter(user=demo_user).first()
    if not dome:
        return HttpResponse("The demo sandbox is temporarily unavailable.", status=503)
    login(
        request,
        demo_user,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    request.session.set_expiry(30 * 60)
    response = redirect("domes:dome-detail", pk=dome.pk)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Cache-Control"] = "no-store"
    return response


@login_required
@rate_limit("profile-update", limit=10, window_seconds=300, authenticated_only=True)
def profile_view(request):
    if is_demo_user(request.user):
        raise PermissionDenied
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user.profile,
    )
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save()
        profile_form.save()
        messages.success(request, "Your account has been updated.")
        return redirect("users:profile")
    return render(
        request,
        "users/profile.html",
        {"u_form": user_form, "p_form": profile_form},
    )


@login_required
def UserSearch(request):
    if is_demo_user(request.user):
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    context = {}
    if query:
        users = (
            User.objects.filter(Q(username__icontains=query), is_active=True)
            .exclude(groups__name="Demo")
            .order_by("username")
        )
        context["users"] = Paginator(users, 10).get_page(request.GET.get("page"))
    return render(request, "messages/search_user.html", context)


def profile_picture(request, username):
    user = User.objects.filter(username=username).first()
    if user is None:
        raise Http404
    if is_demo_user(user) and (
        not request.user.is_authenticated or request.user.pk != user.pk
    ):
        raise Http404
    picture = getattr(user.profile, "picture", None)
    if not picture:
        raise Http404
    try:
        handle, content_type = open_validated_image(
            picture,
            max_bytes=4 * 1024 * 1024,
            max_width=5000,
            max_height=5000,
            max_pixels=16_000_000,
        )
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(handle, content_type=content_type)
    filename = safe_image_filename(picture.name, content_type)
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
