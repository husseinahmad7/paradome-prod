from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views import generic
from django.views.decorators.http import require_POST

from .access import (
    accessible_domes,
    can_access_dome,
    can_administer_dome,
    can_manage_dome,
    can_participate_in_chat,
    is_demo_owned_dome,
    is_demo_user,
)
from .filters import DomeFilter, MembersFilter
from .forms import CategoryCreation, DomeCreation
from .htmx import HtmxTemplateResponseMixin
from .models import Category, Dome
from .presentation import dome_shell_context
from .ratelimits import UserWriteRateLimitMixin, user_write_rate_limit
from .storage import open_validated_image, safe_image_filename


class ExploreDomesView(generic.ListView):
    model = Dome
    template_name = "Domes/explore.html"
    context_object_name = "domes"
    paginate_by = 5

    def get_queryset(self):
        self.filter = DomeFilter(
            self.request.GET,
            queryset=accessible_domes(self.request.user).select_related("user"),
        )
        return self.filter.qs.order_by("-date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter"] = self.filter
        context["can_create_dome"] = (
            self.request.user.is_authenticated
            and not is_demo_user(self.request.user)
        )
        return context

class DomeCreateView(UserWriteRateLimitMixin, LoginRequiredMixin, generic.CreateView):
    model = Dome
    form_class = DomeCreation
    template_name = "Domes/dome_form.html"
    rate_limit_scope = "dome-create"
    rate_limit_count = 5
    success_url = "/dome/"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_demo_user(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class DomeUpdateView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.UpdateView,
):
    model = Dome
    form_class = DomeCreation
    rate_limit_scope = "dome-update"

    def get_queryset(self):
        return accessible_domes(self.request.user)

    def test_func(self):
        return can_administer_dome(self.request.user, self.get_object())


class DomeDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Dome
    success_url = "/dome/"

    def get_queryset(self):
        return accessible_domes(self.request.user)

    def test_func(self):
        return can_administer_dome(self.request.user, self.get_object())


class DomeView(generic.DetailView):
    model = Dome
    template_name = "Domes/dome_detail.html"

    def get_queryset(self):
        return accessible_domes(self.request.user).select_related("user")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(dome_shell_context(self.request.user, self.object))
        return context


class DomeViewHtmx(generic.DetailView):
    model = Dome
    template_name = "Domes/dome_info.html"

    def get_queryset(self):
        return accessible_domes(self.request.user).select_related("user")

    def get(self, request, *args, **kwargs):
        if request.headers.get("HX-Request") == "true":
            return super().get(request, *args, **kwargs)
        return redirect("domes:dome-detail", pk=self.get_object().pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_administer"] = can_administer_dome(
            self.request.user, self.object
        )
        return context


class CategoryCreateView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.FormView,
):
    form_class = CategoryCreation
    template_name = "Domes/category_form.html"
    rate_limit_scope = "category-create"
    rate_limit_count = 15

    def get_dome(self):
        if not hasattr(self, "dome"):
            self.dome = get_object_or_404(Dome, pk=self.kwargs["pk"])
        return self.dome

    def test_func(self):
        return can_manage_dome(self.request.user, self.get_dome())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.get_dome()
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["dome"] = self.get_dome()
        return kwargs

    def form_valid(self, form):
        category = form.save(commit=False)
        category.Dome = self.get_dome()
        category.save()
        return redirect("domes:dome-detail", pk=category.Dome_id)


class DomeInvitationView(
    UserWriteRateLimitMixin, LoginRequiredMixin, generic.DetailView
):
    model = Dome
    template_name = "Domes/invitation.html"
    rate_limit_scope = "dome-invitation"
    rate_limit_count = 10

    def get_object(self, queryset=None):
        dome = get_object_or_404(Dome, invitationstr=self.kwargs["code"])
        if slugify(dome.title) != self.kwargs["slug"] or is_demo_owned_dome(dome):
            raise Http404
        if is_demo_user(self.request.user):
            raise PermissionDenied
        return dome

    def post(self, request, *args, **kwargs):
        dome = self.get_object()
        if request.POST.get("join") != "join":
            return HttpResponse("Invalid invitation action", status=400)
        if request.user != dome.user and not dome.moderators.filter(pk=request.user.pk).exists():
            dome.members.add(request.user)
        return redirect("domes:dome-detail", pk=dome.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_member"] = self.object.members.filter(
            pk=self.request.user.pk
        ).exists()
        return context


class DomeMembersView(
    HtmxTemplateResponseMixin,
    LoginRequiredMixin,
    generic.ListView,
):
    partial_template_name = "Domes/members_list.html"
    page_template_name = "Domes/dome_members_page.html"
    context_object_name = "members"
    paginate_by = 20

    def get_dome(self):
        if not hasattr(self, "dome"):
            self.dome = get_object_or_404(Dome.objects.select_related("user"), pk=self.kwargs["pk"])
        if not can_participate_in_chat(self.request.user, self.dome):
            raise PermissionDenied
        return self.dome

    def get_queryset(self):
        self.filter = MembersFilter(
            self.request.GET, queryset=self.get_dome().members.all()
        )
        return self.filter.qs.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dome = self.get_dome()
        context.update(
            {
                "filter": self.filter,
                "mods": dome.moderators.all(),
                "dome_owner": dome.user,
                "dome_pk": dome.pk,
            }
        )
        context.update(
            dome_shell_context(
                self.request.user,
                dome,
                active_section="members",
            )
        )
        return context


class UserDomesView(LoginRequiredMixin, generic.ListView):
    template_name = "Domes/user_domes.html"
    context_object_name = "owned"

    def get_queryset(self):
        return accessible_domes(
            self.request.user, self.request.user.server_owner.all()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["admin"] = accessible_domes(
            self.request.user, self.request.user.dome_moderators.all()
        )
        context["member"] = accessible_domes(
            self.request.user, self.request.user.dome_members.all()
        )
        return context


@login_required
@require_POST
@user_write_rate_limit("member-remove", limit=20)
def MemberRemoveView(request, dome_id, user_id):
    dome = get_object_or_404(Dome, pk=dome_id)
    removed = get_object_or_404(User, pk=user_id)
    if not can_manage_dome(request.user, dome) or removed == dome.user:
        raise PermissionDenied
    if request.user == dome.user:
        dome.members.remove(removed)
        dome.moderators.remove(removed)
    elif dome.moderators.filter(pk=request.user.pk).exists():
        if dome.moderators.filter(pk=removed.pk).exists():
            raise PermissionDenied
        dome.members.remove(removed)
    if request.headers.get("HX-Request") == "true":
        return HttpResponse("")
    return redirect("domes:dome-members", pk=dome.pk)


@login_required
@require_POST
@user_write_rate_limit("member-role", limit=20)
def ModeratorRaiseOrDown(request, pk, user_pk, option):
    dome = get_object_or_404(Dome, pk=pk)
    selected_user = get_object_or_404(User, pk=user_pk)
    if not can_administer_dome(request.user, dome) or selected_user == dome.user:
        raise PermissionDenied
    if option == 0 and dome.moderators.filter(pk=selected_user.pk).exists():
        dome.moderators.remove(selected_user)
        dome.members.add(selected_user)
    elif option == 1 and dome.members.filter(pk=selected_user.pk).exists():
        dome.members.remove(selected_user)
        dome.moderators.add(selected_user)
    else:
        return HttpResponse("Invalid role transition", status=400)
    if request.headers.get("HX-Request") == "true":
        return HttpResponse("")
    return redirect("domes:dome-members", pk=dome.pk)


def dome_media(request, pk, kind):
    dome = get_object_or_404(Dome, pk=pk)
    if not can_access_dome(request.user, dome):
        raise PermissionDenied
    if kind not in {"icon", "banner"}:
        raise Http404
    image = getattr(dome, kind)
    if not image:
        raise Http404
    try:
        handle, content_type = open_validated_image(
            image,
            max_bytes=5 * 1024 * 1024,
            max_width=7000,
            max_height=7000,
            max_pixels=24_000_000,
        )
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(handle, content_type=content_type)
    filename = safe_image_filename(image.name, content_type)
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
