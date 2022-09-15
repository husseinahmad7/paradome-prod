from django.db.models.expressions import F
from django.http.response import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.views import generic
from django.utils import timezone
from posts.models import Comment, Post, Stream, Tag, Like, Follow
from django.contrib.auth.mixins import LoginRequiredMixin,UserPassesTestMixin
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from .forms import CommentCreation, PostCreation, TagCreation,CommentReplyCreation
from django.urls import reverse
from users.models import Profile
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.paginator import Paginator
from posts.filters import PostFilter
from Domes.models import Dome
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.db.models import Q

class PostsList(generic.ListView):
    model = Post
    template_name = 'posts/posts.html'
    # context_object_name = 'latest_posts_list' # overriding the default/ question = question_list
    # paginate_by = 10
    #ordering = ['-pub_date']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        posts = Post.objects.filter(Q(posted_date__lte=timezone.now()), Q(dome__isnull=True) | Q(dome__privacy__exact=1)).order_by('-posted_date')
        filter = PostFilter(self.request.GET, queryset=posts)
        posts = filter.qs
        paginator = Paginator(posts, 10) # paging the comments
        context['paginator']= paginator
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context['is_paginated'] = page_obj.has_other_pages()
        user = self.request.user
        liked = set()
        if self.request.user.is_authenticated:
            for post in posts:
                is_liked = Like.objects.filter(user=user, post=post).count()
                if is_liked == 1:
                    liked.add(post.pk)
            context['likedset'] = liked
        
        context['page_obj'] = page_obj
        context['filter'] = filter
        return context
        
    # def get_queryset(self):
    #     return Post.objects.filter(posted_date__lte=timezone.now()).order_by('-posted_date') # [:5]

class UserPostsList(generic.ListView):
    template_name = 'posts/user_posts.html'
    context_object_name = 'latest_posts_list'
    paginate_by = 5
    
    def get_queryset(self):
        user = get_object_or_404(User, username=self.kwargs.get('username'))
        return Post.objects.filter(Q(user=user),
                                   Q(posted_date__lte=timezone.now()), Q(dome__isnull=True) | Q(dome__privacy__exact=1)).order_by('-posted_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = get_object_or_404(User, username=self.kwargs.get('username'))
        
        profile = get_object_or_404(Profile,user=user)
        posts_count =Post.objects.filter(user=user).count()
        following_count = Follow.objects.filter(follower=user).count
        followers_count = Follow.objects.filter(following=user).count
        if self.request.user.is_authenticated:
            follow_status = Follow.objects.filter(following=user, follower= self.request.user).exists()
        else:
            follow_status = False
            
        visitor = self.request.user
        liked = set()
        if self.request.user.is_authenticated:
            for post in self.get_queryset():
                is_liked = Like.objects.filter(user=visitor, post=post).count()
                if is_liked == 1:
                    liked.add(post.pk)
            context['likedset'] = liked

        context['profile'] = profile
        context['posts_count']= posts_count
        context['following_count']= following_count
        context['followers_count']= followers_count
        context['follow_status'] = follow_status
        return context

class PostView(generic.edit.ModelFormMixin ,generic.DetailView):
    model = Post
    template_name = 'posts/post.html'
    form_class = CommentCreation
    
    def post(self,request, *args, **kwargs):

        form = CommentCreation(self.request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = get_object_or_404(Post, pk=self.kwargs.get('pk'))
            comment.user =self.request.user
            comment.save()
            return HttpResponseRedirect(reverse('posts:post-detail', args=[self.kwargs.get('pk')]))
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = self.get_form() # form
        post = get_object_or_404(Post, pk=self.kwargs.get('pk')) # comments
        comments=post.comments.filter(reply_to=None)
        paginator = Paginator(comments, 10) # paging the comments
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context['page_obj'] = page_obj
        user = self.request.user
        if self.request.user.is_authenticated:
            liked = Like.objects.filter(user=user, post=post).count()
            if liked == 1:
                context['liked'] = True
            else:
                context['liked'] = False
            # save post
            context['favorite'] = False
            profile = Profile.objects.get(user=self.request.user)
            if profile.favorite.filter(pk=self.kwargs.get('pk')).exists():
                context['favorite'] = True
            if post.dome is not None:
                context['dome_owner'] = post.dome.user
                context['dome_mods'] = post.dome.moderators
        return context


class PostCreateView(LoginRequiredMixin,generic.CreateView):
    model = Post
    # fields =['picture','question_text','content','tags']
    form_class = PostCreation
    
    def post(self,request, *args, **kwargs):
        form = PostCreation(self.request.POST, self.request.FILES)
        if form.is_valid():
            tags_objs = []
            form_picture = form.cleaned_data.get('picture')
            form_q = form.cleaned_data.get('question_text')
            form_content = form.cleaned_data.get('content')
            form_tags = form.cleaned_data.get('tags')
            # tags_list =list(form_tags.split(','))
            # for tag in tags_list:
            #     t,created = Tag.objects.get_or_create(title=tag.strip())
            #     tags_objs.append(t)
            
            p,created = Post.objects.get_or_create(question_text=form_q, picture=form_picture, user=self.request.user, content=form_content )
            p.tags.set(form_tags)
            p.save()
            return HttpResponseRedirect(reverse('posts:post-detail', args=[p.pk]))
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

# Dome post creating
class DomePostCreateView(LoginRequiredMixin, UserPassesTestMixin, generic.DetailView, generic.edit.FormMixin):
    model = Dome
    form_class = PostCreation
    template_name = 'posts/post_form.html'
    # def get_object(self, request,*args, **kwargs):
    #     dome_obj = get_object_or_404(Dome, id=self.kwargs.get('pk'))
    #     return dome_obj
    
    def post(self,request, *args, **kwargs):
        form = PostCreation(self.request.POST, self.request.FILES)
        if form.is_valid():
            dome = self.get_object()
            tags_objs = []
            form_picture = form.cleaned_data.get('picture')
            form_q = form.cleaned_data.get('question_text')
            form_content = form.cleaned_data.get('content')
            form_tags = form.cleaned_data.get('tags')
            # tags_list =list(form_tags.split(','))
            # for tag in tags_list:
            #     t,created = Tag.objects.get_or_create(title=tag.strip())
            #     tags_objs.append(t)
            
            p,created = Post.objects.get_or_create(question_text=form_q, picture=form_picture, user=self.request.user, content=form_content, dome=dome)
            p.tags.set(form_tags)
            p.save()
            return HttpResponseRedirect(reverse('posts:post-detail', args=[p.pk]))
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)
    
    def test_func(self):
        dome = self.get_object()
        moderators = dome.moderators.all()
        user = self.request.user
        if (dome.user == user) | (user in moderators):
            return True
        else:
            return False


class PostUpdateView(LoginRequiredMixin, UserPassesTestMixin, generic.UpdateView):
    model = Post
    # fields =['picture','question_text','content','tags']
    form_class = PostCreation
    
    # def post(self,request, *args, **kwargs):
    #     form = PostCreation(self.request.POST, self.request.FILES)
    #     if form.is_valid():
    #         tags_objs = []
    #         form_picture = form.cleaned_data.get('picture')
    #         form_q = form.cleaned_data.get('question_text')
    #         form_content = form.cleaned_data.get('content')
    #         form_tags = form.cleaned_data.get('tags')
    #         # tags_list =list(form_tags.split(','))
    #         # for tag in form_tags:
    #             # if tag.strip().startswith('[<Tag: '):
    #             #     tag = tag[7:]
    #             # if tag.strip().startswith('<Tag: '):
    #             #     tag = tag[6:]
    #             # if tag.strip().endswith('>]') or tag.strip().endswith('>') or tag.strip().endswith(']'):
    #             #     i = tag.find('>')
    #             #     tag = tag[:i]
    #             # t,created = Tag.objects.get_or_create(title=tag.strip())
    #             # tags_objs.append(t)
    #         # post = self.get_object()
    #         p = Post.objects.all().filter(pk=self.kwargs['pk'])
    #         p.update(question_text=form_q, picture=form_picture, content=form_content)
    #         # p,created = Post.objects.get_or_create(question_text=form_q, picture=form_picture, user=self.request.user, content=form_content )
    #         # post.set(tags=tags_objs)
    #         p.get(pk=self.kwargs['pk']).tags.set(form_tags)
    #         # p.tags.set(tags_objs)
            
    #         return HttpResponseRedirect(reverse('posts:post-detail', args=[self.kwargs['pk']]))

    def test_func(self):
        post = self.get_object()
        if self.request.user == post.user:
            return True
        return False
    
class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, generic.DeleteView):
    model = Post
    success_url= '/posts/'
    def test_func(self):
        post = self.get_object()
        if self.request.user == post.user:
            return True
        return False


class StreamView(LoginRequiredMixin, generic.ListView):
    template_name = 'posts/stream.html'
    context_object_name = 'latest_posts_list' # overriding the default/ question = question_list
    paginate_by = 5
    #ordering = ['-pub_date']
    def get_queryset(self):
        user = self.request.user
        posts = Stream.objects.filter(user=user)
        ids = []
        for post in posts:
            ids.append(post.post.pk)
            
        return Post.objects.filter(pk__in=ids, posted_date__lte=timezone.now()).order_by('-posted_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visitor = self.request.user
        liked = set()
        if self.request.user.is_authenticated:
            for post in self.get_queryset():
                is_liked = Like.objects.filter(user=visitor, post=post).count()
                if is_liked == 1:
                    liked.add(post.pk)
            context['likedset'] = liked
        return context
    

class UserFavoritesList(LoginRequiredMixin, generic.ListView):
    template_name = 'posts/profile_favorites.html'
    context_object_name = 'favorites_list'
    paginate_by = 20
    
    def get_queryset(self):
        user = get_object_or_404(User, username=self.kwargs.get('username'))
        return user.profile.favorite.filter(posted_date__lte=timezone.now()).order_by('-posted_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter = PostFilter(self.request.GET, queryset=self.get_queryset())
        posts = filter.qs
        paginator = Paginator(posts, 5) # paging the comments
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        visitor = self.request.user
        liked = set()
        if self.request.user.is_authenticated:
            for post in self.get_queryset():
                is_liked = Like.objects.filter(user=visitor, post=post).count()
                if is_liked == 1:
                    liked.add(post.pk)
            context['likedset'] = liked
        context['favorites_list'] = page_obj
        context['filter'] = filter
        return context
    
    
@login_required
def like(request,pk):
    user = request.user
    post = Post.objects.filter(pk=pk)
    # current_likes = post.likes
    liked = Like.objects.filter(user=user, post=post.first()).count()
    if liked == 0:
        Like.objects.create(user=user,post=post.first())
        post.update(likes = F('likes') + 1)
        likes = post.first().likes
        return TemplateResponse(request,'posts/like.html',{'liked':True,'pk':pk,'likes':likes})
    else:
        Like.objects.filter(user=user,post=post.first()).delete()
        post.update(likes = F('likes') - 1)
        likes = post.first().likes
        return TemplateResponse(request, 'posts/like.html',{'liked':False,'pk':pk,'likes':likes})
    # post.likes = current_likes
    # post.save()
    
    # return HttpResponseRedirect(reverse('posts:post-detail', args=(pk,)))

@login_required
def favorites(request, pk):
        user = request.user
        post = Post.objects.get(pk=pk)
        profile = Profile.objects.get(user=user)
        
        if profile.favorite.filter(pk=pk).exists():
            profile.favorite.remove(post)
        else:
            profile.favorite.add(post)
        return HttpResponseRedirect(reverse('posts:post-detail', args=[pk]))

@login_required
def follow(request, username, option):
    user =request.user
    following = get_object_or_404(User, username=username)
    
    try:
        f,created = Follow.objects.get_or_create(follower=user, following=following)
        if int(option) == 0:
            f.delete()
            Stream.objects.filter(following=following, user=user).all().delete()
        else:
            posts = Post.objects.all().filter(user=following)[:10]
            
            with transaction.atomic():
                for post in posts:
                    stream = Stream(post=post, user=user, following=following, date=post.posted_date)
                    stream.save()
        return HttpResponseRedirect(reverse('posts:user-posts', args=[username]))
    except User.DoesNotExist:
        return HttpResponseRedirect(reverse('posts:user-posts', args=[username]))

class TagCreationView(LoginRequiredMixin,generic.CreateView):
    model = Tag
    form_class = TagCreation
    
class HtmxDomePostsView(LoginRequiredMixin,UserPassesTestMixin,generic.ListView):
    model = Post
    template_name = 'domes/dome_detail_posts.html'
    paginate_by = 5
    
    def get_dome_object(self, pk):
        dome = get_object_or_404(Dome, pk=pk)
        return dome
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dome_obj = self.get_dome_object(self.kwargs.get('pk'))
        dome_id = dome_obj.id
        posts = Post.objects.filter(posted_date__lte=timezone.now(),dome=dome_obj).order_by('-posted_date')
        filter = PostFilter(self.request.GET, queryset=posts)
        posts = filter.qs
        paginator = Paginator(posts, 5)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        user = self.request.user
        liked = set()
        if self.request.user.is_authenticated:
            for post in posts:
                is_liked = Like.objects.filter(user=user, post=post).count()
                if is_liked == 1:
                    liked.add(post.pk)
            context['likedset'] = liked
        context['object'] = page_obj
        context['filter'] = filter
        context['dome_id'] = dome_id
        return context
    
    def test_func(self):
        dome_obj = self.get_dome_object(self.kwargs.get('pk'))
        dome_owner = dome_obj.user
        dome_members = dome_obj.members.all()
        dome_privacy = dome_obj.privacy
        if (self.request.user == dome_owner) | (self.request.user in dome_members) | (dome_privacy ==1):
            return True
        return False
    
class RepliesListView(LoginRequiredMixin, generic.ListView):
    template_name = 'posts/replies_list.html'
    context_object_name = 'replies'
    paginate_by = 20
    
    def post(self,request, *args, **kwargs):

        form = CommentReplyCreation(self.request.POST)
        if form.is_valid():
            commenttxt = form.cleaned_data.get('comment')
            post_pk = self.get_comment().post.pk
            post = get_object_or_404(Post, pk=post_pk)
            user =self.request.user
            reply_to_com = self.get_comment()
            Reply, created = Comment.objects.get_or_create(post=post,user=user,comment=commenttxt,reply_to=reply_to_com)
            if created:
                Reply.save()
            return HttpResponseRedirect(reverse('posts:comment-replies', args=[self.kwargs.get('pk')]))
        
    def get_comment(self):
        return get_object_or_404(Comment, pk=self.kwargs.get('pk'))
    def get_queryset(self):
        comment = self.get_comment()
        return comment.children.all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comment_id'] = self.kwargs.get('pk')
        context['form'] = CommentReplyCreation()
        if self.request.user.is_authenticated:
            comment = self.get_comment()
            post = comment.post
            if post.dome is not None:
                context['dome_owner'] = post.dome.user
                context['dome_mods'] = post.dome.moderators
        return context

@login_required
def deleteComment(request,comment_id):
    if request.method == 'DELETE':
        user = request.user
        comment = get_object_or_404(Comment, pk=comment_id)
        post = comment.post
        dome = post.dome
        if dome is not None:
            if user == dome.user or user in dome.moderators.all():
                comment.delete()
                return HttpResponse('Comment deleted')
            elif comment.user == user:
                comment.delete()
                return HttpResponse('Comment deleted')
            else:
                HttpResponseForbidden('Not allowed')
        elif comment.user == user:
            comment.delete()
            return HttpResponse('Comment deleted')
        else:
            HttpResponseForbidden('Not allowed')
    else:
        HttpResponseForbidden('Not allowed')


        