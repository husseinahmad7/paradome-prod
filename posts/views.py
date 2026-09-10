from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views import generic
from django.views.decorators.http import require_POST

from Domes.access import can_access_dome, can_create_dome_content, is_demo_user
from Domes.models import Dome
from Domes.ratelimits import UserWriteRateLimitMixin, user_write_rate_limit
from Domes.storage import open_validated_image, safe_image_filename
from users.models import Profile

from .access import accessible_posts, can_access_post, can_moderate_post
from .filters import PostFilter
from .forms import CommentCreation, CommentReplyCreation, PostCreation, TagCreation
from .models import Comment, Follow, Like, Post, Stream, Tag


def _liked_post_ids(user, queryset):
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(
        Like.objects.filter(user=user, post__in=queryset).values_list(
            "post_id", flat=True
        )
    )


def _visible_post_or_404(request, pk):
    return get_object_or_404(
        accessible_posts(request.user).select_related("dome", "dome__user"),
        pk=pk,
    )


def _can_interact(user, post):
    if not getattr(user, "is_authenticated", False) or not can_access_post(user, post):
        return False
    if is_demo_user(user):
        return post.dome_id is not None and post.dome.user_id == user.pk
    return True


class PostsList(generic.ListView):
    model = Post
    template_name = "posts/posts.html"
    context_object_name = "latest_posts_list"
    paginate_by = 10

    def get_queryset(self):
        queryset = accessible_posts(self.request.user).filter(
            posted_date__lte=timezone.now()
        )
        self.filter = PostFilter(
            self.request.GET,
            queryset=queryset.select_related("user", "dome").prefetch_related("tags"),
        )
        return self.filter.qs.order_by("-posted_date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_posts = context.get("page_obj", context["object_list"])
        context["likedset"] = _liked_post_ids(self.request.user, page_posts)
        context["filter"] = self.filter
        return context


class UserPostsList(generic.ListView):
    template_name = "posts/user_posts.html"
    context_object_name = "latest_posts_list"
    paginate_by = 5

    def get_profile_user(self):
        queryset = User.objects.all()
        if is_demo_user(self.request.user):
            queryset = queryset.filter(pk=self.request.user.pk)
        else:
            queryset = queryset.exclude(groups__name="Demo")
        return get_object_or_404(queryset, username=self.kwargs["username"])

    def get_queryset(self):
        self.profile_user = self.get_profile_user()
        return (
            accessible_posts(self.request.user)
            .filter(user=self.profile_user, posted_date__lte=timezone.now())
            .select_related("user", "dome")
            .prefetch_related("tags")
            .order_by("-posted_date")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target = self.profile_user
        context.update(
            {
                "profile": get_object_or_404(Profile, user=target),
                "posts_count": self.get_queryset().count(),
                "following_count": Follow.objects.filter(follower=target).count(),
                "followers_count": Follow.objects.filter(following=target).count(),
                "follow_status": (
                    self.request.user.is_authenticated
                    and not is_demo_user(self.request.user)
                    and Follow.objects.filter(
                        following=target, follower=self.request.user
                    ).exists()
                ),
            }
        )
        page_posts = context.get("page_obj", context["object_list"])
        context["likedset"] = _liked_post_ids(self.request.user, page_posts)
        return context


class PostView(UserWriteRateLimitMixin, generic.edit.ModelFormMixin, generic.DetailView):
    model = Post
    template_name = "posts/post.html"
    form_class = CommentCreation
    rate_limit_scope = "comment-create"
    rate_limit_count = 30

    def get_object(self, queryset=None):
        return _visible_post_or_404(self.request, self.kwargs["pk"])

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("users:login")
        self.object = self.get_object()
        if not _can_interact(request.user, self.object):
            raise PermissionDenied
        form = self.get_form()
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = self.object
            comment.user = request.user
            comment.save()
            return redirect("posts:post-detail", pk=self.object.pk)
        return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        comments = post.comments.filter(reply_to=None).select_related("user")
        paginator = Paginator(comments, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context["page_obj"] = page_obj
        context["liked"] = (
            self.request.user.is_authenticated
            and Like.objects.filter(user=self.request.user, post=post).exists()
        )
        context["favorite"] = (
            self.request.user.is_authenticated
            and not is_demo_user(self.request.user)
            and Profile.objects.filter(
                user=self.request.user, favorite=post
            ).exists()
        )
        context["can_favorite"] = (
            self.request.user.is_authenticated
            and not is_demo_user(self.request.user)
        )
        context["can_moderate_comments"] = (
            self.request.user.is_authenticated
            and can_moderate_post(self.request.user, post)
        )
        return context


class PostCreateView(UserWriteRateLimitMixin, LoginRequiredMixin, generic.CreateView):
    model = Post
    form_class = PostCreation
    rate_limit_scope = "post-create"
    rate_limit_count = 12

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_demo_user(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class DomePostCreateView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.FormView,
):
    form_class = PostCreation
    template_name = "posts/post_form.html"
    rate_limit_scope = "dome-post-create"
    rate_limit_count = 20

    def get_dome(self):
        if not hasattr(self, "dome"):
            self.dome = get_object_or_404(Dome.objects.select_related("user"), pk=self.kwargs["pk"])
        return self.dome

    def test_func(self):
        return can_create_dome_content(self.request.user, self.get_dome())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.get_dome()
        return context

    def form_valid(self, form):
        post = form.save(commit=False)
        post.user = self.request.user
        post.dome = self.get_dome()
        post.save()
        form.save_m2m()
        return redirect("posts:post-detail", pk=post.pk)


class PostUpdateView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.UpdateView,
):
    model = Post
    form_class = PostCreation
    rate_limit_scope = "post-update"

    def get_queryset(self):
        return accessible_posts(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def test_func(self):
        return can_moderate_post(self.request.user, self.get_object())


class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Post
    success_url = "/posts/"

    def get_queryset(self):
        return accessible_posts(self.request.user)

    def test_func(self):
        return can_moderate_post(self.request.user, self.get_object())


class StreamView(LoginRequiredMixin, generic.ListView):
    template_name = "posts/stream.html"
    context_object_name = "latest_posts_list"
    paginate_by = 5

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and is_demo_user(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        stream_ids = Stream.objects.filter(user=self.request.user).values("post_id")
        return (
            accessible_posts(self.request.user)
            .filter(pk__in=stream_ids, posted_date__lte=timezone.now())
            .order_by("-posted_date")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["likedset"] = _liked_post_ids(
            self.request.user, context.get("page_obj", context["object_list"])
        )
        return context


class UserFavoritesList(LoginRequiredMixin, generic.ListView):
    template_name = "posts/profile_favorites.html"
    context_object_name = "favorites_list"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            is_demo_user(request.user)
            or request.user.username != self.kwargs["username"]
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = accessible_posts(self.request.user).filter(
            pk__in=self.request.user.profile.favorite.values("pk"),
            posted_date__lte=timezone.now(),
        )
        self.filter = PostFilter(self.request.GET, queryset=queryset)
        return self.filter.qs.order_by("-posted_date")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["likedset"] = _liked_post_ids(
            self.request.user, context.get("page_obj", context["object_list"])
        )
        context["filter"] = self.filter
        return context


@login_required
@require_POST
@user_write_rate_limit("like", limit=60)
def like(request, pk):
    post = _visible_post_or_404(request, pk)
    if not _can_interact(request.user, post):
        raise PermissionDenied

    with transaction.atomic():
        locked_post = Post.objects.select_for_update().get(pk=post.pk)
        existing = Like.objects.filter(user=request.user, post=locked_post).first()
        if existing:
            existing.delete()
            liked = False
        else:
            Like.objects.create(user=request.user, post=locked_post)
            liked = True
        likes = Like.objects.filter(post=locked_post).count()
        Post.objects.filter(pk=locked_post.pk).update(likes=likes)

    return TemplateResponse(
        request,
        "posts/like.html",
        {"liked": liked, "pk": pk, "likes": likes},
    )


@login_required
@require_POST
@user_write_rate_limit("favorite", limit=40)
def favorites(request, pk):
    if is_demo_user(request.user):
        raise PermissionDenied
    post = _visible_post_or_404(request, pk)
    profile = get_object_or_404(Profile, user=request.user)
    if profile.favorite.filter(pk=post.pk).exists():
        profile.favorite.remove(post)
    else:
        profile.favorite.add(post)
    return redirect("posts:post-detail", pk=post.pk)


@login_required
@require_POST
@user_write_rate_limit("follow", limit=30)
def follow(request, username, option):
    if is_demo_user(request.user):
        raise PermissionDenied
    following = get_object_or_404(
        User.objects.exclude(groups__name="Demo"), username=username
    )
    if following == request.user:
        return HttpResponseBadRequest("You cannot follow yourself.")
    if option not in {"0", "1"}:
        return HttpResponseBadRequest("Invalid follow action.")

    with transaction.atomic():
        User.objects.select_for_update().get(pk=following.pk)
        if option == "0":
            Follow.objects.filter(
                follower=request.user, following=following
            ).delete()
            Stream.objects.filter(user=request.user, following=following).delete()
        else:
            _, created = Follow.objects.get_or_create(
                follower=request.user, following=following
            )
            if created:
                recent_posts = Post.objects.filter(
                    user=following,
                    dome__isnull=True,
                    posted_date__lte=timezone.now(),
                ).order_by("-posted_date")[:10]
                Stream.objects.bulk_create(
                    [
                        Stream(
                            following=following,
                            user=request.user,
                            post=post,
                            date=post.posted_date,
                        )
                        for post in recent_posts
                    ],
                    ignore_conflicts=True,
                )
    return redirect("posts:user-posts", username=username)


class TagCreationView(
    UserWriteRateLimitMixin,
    LoginRequiredMixin,
    UserPassesTestMixin,
    generic.CreateView,
):
    model = Tag
    form_class = TagCreation
    rate_limit_scope = "tag-create"
    rate_limit_count = 15

    def test_func(self):
        return not is_demo_user(self.request.user)


class HtmxDomePostsView(generic.ListView):
    model = Post
    template_name = "Domes/dome_detail_posts.html"
    paginate_by = 5

    def get_dome(self):
        if not hasattr(self, "dome"):
            self.dome = get_object_or_404(Dome.objects.select_related("user"), pk=self.kwargs["pk"])
        if not can_access_dome(self.request.user, self.dome):
            raise PermissionDenied
        return self.dome

    def get_queryset(self):
        dome = self.get_dome()
        queryset = Post.objects.filter(
            posted_date__lte=timezone.now(), dome=dome
        ).order_by("-posted_date")
        self.filter = PostFilter(self.request.GET, queryset=queryset)
        return self.filter.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page_posts = context.get("page_obj", context["object_list"])
        context.update(
            {
                "object": page_posts,
                "filter": self.filter,
                "dome_id": self.get_dome().pk,
                "likedset": _liked_post_ids(self.request.user, page_posts),
                "can_create_post": (
                    self.request.user.is_authenticated
                    and can_create_dome_content(self.request.user, self.get_dome())
                ),
            }
        )
        return context


class RepliesListView(UserWriteRateLimitMixin, generic.ListView):
    template_name = "posts/replies_list.html"
    context_object_name = "replies"
    paginate_by = 20
    rate_limit_scope = "reply-create"
    rate_limit_count = 30

    def get_comment(self):
        comment = get_object_or_404(
            Comment.objects.select_related("post", "post__dome", "post__dome__user"),
            pk=self.kwargs["pk"],
        )
        if not can_access_post(self.request.user, comment.post):
            raise PermissionDenied
        return comment

    def get_queryset(self):
        return self.get_comment().children.select_related("user")

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        parent = self.get_comment()
        if not _can_interact(request.user, parent.post):
            raise PermissionDenied
        form = CommentReplyCreation(request.POST)
        if form.is_valid():
            Comment.objects.create(
                post=parent.post,
                user=request.user,
                comment=form.cleaned_data["comment"],
                reply_to=parent,
            )
            return redirect("posts:comment-replies", pk=parent.pk)
        self.object_list = self.get_queryset()
        return self.render_to_response(self.get_context_data(form=form), status=400)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parent = self.get_comment()
        context.setdefault("form", CommentReplyCreation())
        context["comment_id"] = parent.pk
        context["can_moderate_comments"] = (
            self.request.user.is_authenticated
            and can_moderate_post(self.request.user, parent.post)
        )
        return context


@login_required
@require_POST
@user_write_rate_limit("comment-delete", limit=30)
def deleteComment(request, comment_id):
    comment = get_object_or_404(
        Comment.objects.select_related("post", "post__dome", "post__dome__user"),
        pk=comment_id,
    )
    if not can_access_post(request.user, comment.post):
        raise PermissionDenied
    if comment.user_id != request.user.pk and not can_moderate_post(
        request.user, comment.post
    ):
        raise PermissionDenied
    comment.delete()
    return HttpResponse("")


def post_picture(request, pk):
    post = _visible_post_or_404(request, pk)
    if not post.picture:
        raise Http404
    try:
        handle, content_type = open_validated_image(
            post.picture,
            max_bytes=4 * 1024 * 1024,
            max_width=6000,
            max_height=6000,
            max_pixels=20_000_000,
        )
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(handle, content_type=content_type)
    filename = safe_image_filename(post.picture.name, content_type)
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    response.headers["Cache-Control"] = "private, max-age=300"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
