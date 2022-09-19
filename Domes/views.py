from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.shortcuts import render
from django.views import generic
from .models import Dome, Category
from .filters import DomeFilter, MembersFilter
from .forms import DomeCreation, CategoryCreation
from django.http.response import HttpResponseRedirect, HttpResponse, HttpResponseForbidden
from django.urls import reverse
from django.contrib.auth.mixins import LoginRequiredMixin,UserPassesTestMixin
from django.core.paginator import Paginator
from django.utils.text import slugify
from django.http import Http404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required




class ExploreDomesView(generic.ListView):
    model = Dome
    template_name = 'Domes/explore.html'
    context_object_name = 'domes'
    paginate = 10

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        Domes = Dome.objects.filter(privacy=1).order_by('date')
        filter = DomeFilter(self.request.GET, queryset=Domes)
        Domes = filter.qs
        paginator = Paginator(Domes, 5)
        page_number = self.request.GET.get('page')
        Domes = paginator.get_page(page_number)
        context['domes'] = Domes
        context['filter'] = filter
        return context

    # def get_queryset(self):
    #     return Dome.objects.filter(date__lte=timezone.now()).order_by('-date') # [:5]

class DomeCreateView(LoginRequiredMixin, generic.CreateView):
    model = Dome
    form_class = DomeCreation
    template_name = 'Domes/dome_form.html'

    def post(self, request, *args, **kwargs):
        form = DomeCreation(self.request.POST, self.request.FILES)
        if form.is_valid():
            user =self.request.user
            form_pic = form.cleaned_data.get('icon')
            form_banner = form.cleaned_data.get('banner')
            form_title = form.cleaned_data.get('title')
            form_description = form.cleaned_data.get('description')
            form_privacy = form.cleaned_data.get('privacy')

            dome,created = Dome.objects.get_or_create(icon=form_pic,banner=form_banner,title=form_title,description=form_description, user = user,privacy=form_privacy )
            dome.save()
            return HttpResponseRedirect(reverse('domes:explore')) #fix url latter

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

class DomeUpdateView(LoginRequiredMixin,UserPassesTestMixin , generic.UpdateView):
    model = Dome
    form_class = DomeCreation

    def test_func(self):
        if self.get_object().user == self.request.user:
            return True
        return False

class DomeDeleteView(LoginRequiredMixin,UserPassesTestMixin , generic.DeleteView):
    model = Dome
    form_class = DomeCreation
    success_url = '/domes'

    def test_func(self):
        if self.get_object().user == self.request.user:
            return True
        return False
class DomeView(LoginRequiredMixin,UserPassesTestMixin,generic.DetailView):
    model = Dome
    template_name = 'Domes/dome_detail.html'

    def test_func(self):
        dome_obj = self.get_object()
        dome_owner = dome_obj.user
        dome_members = dome_obj.members.all()
        dome_mod = dome_obj.moderators.all()
        dome_privacy = dome_obj.privacy
        if (self.request.user == dome_owner) | (self.request.user in dome_members) | (self.request.user in dome_mod) | (dome_privacy ==1):
            return True
        return False

class DomeViewHtmx(LoginRequiredMixin,UserPassesTestMixin,generic.DetailView):
    model = Dome
    template_name = 'Domes/dome_info.html'

    def get(self, request, *args, **kwargs):
        if 'HX-Request' in self.request.headers.keys() and self.request.headers.get('HX-Request') == 'true':
            return super(DomeViewHtmx, self).get(request, *args, **kwargs)
        else:
            return HttpResponseRedirect(reverse('domes:dome-detail',args=[self.get_object().pk]))
    def test_func(self):

        dome_obj = self.get_object()
        dome_owner = dome_obj.user
        dome_members = dome_obj.members.all()
        dome_mod = dome_obj.moderators.all()
        dome_privacy = dome_obj.privacy
        if (self.request.user == dome_owner) | (self.request.user in dome_members) | (self.request.user in dome_mod) | (dome_privacy ==1):
            return True
        return False


class CategoryCreateView(LoginRequiredMixin,generic.DetailView, generic.edit.FormMixin):
    model = Dome
    form_class = CategoryCreation
    template_name = 'Domes/category_form.html'
    def post(self, request, *args, **kwargs):
        form = CategoryCreation(self.request.POST)
        if form.is_valid():
            dome_obj = get_object_or_404(Dome, pk= self.kwargs.get('pk'))
            title = form.cleaned_data.get('title')
            c = Category(title=title, Dome=dome_obj)
            c.save()
            return HttpResponseRedirect(reverse('domes:dome-detail',args=[dome_obj.pk]))

class DomeInvitationView(LoginRequiredMixin, generic.DetailView):
    model = Dome
    template_name = 'Domes/invitation.html'

    def get_object(self):
        code = self.kwargs.get('code')
        slug = self.kwargs.get('slug')
        dome_obj = get_object_or_404(Dome, invitationstr = code)
        if slugify(dome_obj.title) == slug:
            return dome_obj
        else:
            raise Http404

    def post(self, request, *args, **kwargs):
        if self.request.POST.get('join') == 'join':
            obj = self.get_object()
            visitor = self.request.user
            obj.members.add(visitor)
            return HttpResponseRedirect(reverse('domes:dome-detail',args=[obj.pk]))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visitor = self.request.user
        if visitor in self.get_object().members.all():
            context['is_member'] = True
        else:
            context['is_member'] = False
        return context

class DomeMembersView(LoginRequiredMixin,UserPassesTestMixin, generic.ListView):
    template_name = 'Domes/members_list.html'
    context_object_name = 'members'
    paginate_by = 20

    def get_object(self):
        dome = get_object_or_404(Dome, pk=self.kwargs.get('pk'))
        return dome
    def get_queryset(self):
        dome = self.get_object()
        members = dome.members.all()
        return members

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dome = self.get_object()
        moderators = dome.moderators.all()
        filter = MembersFilter(self.request.GET, queryset=self.get_queryset())
        members = filter.qs
        paginator = Paginator(members, 20) # paging the comments
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        context['members'] = page_obj
        context['filter'] = filter
        context['mods'] = moderators
        context['dome_owner'] = dome.user
        context['dome_pk'] = dome.pk
        return context

    def test_func(self):

        dome_obj = self.get_object()
        dome_owner = dome_obj.user
        dome_members = dome_obj.members.all()
        dome_mod = dome_obj.moderators.all()
        if (self.request.user == dome_owner) | (self.request.user in dome_members) | (self.request.user in dome_mod):
            return True
        return False

class UserDomesView(LoginRequiredMixin, generic.ListView):
    template_name = 'Domes/user_domes.html'
    context_object_name = 'owned'

    def get_queryset(self):
        user = self.request.user
        return user.server_owner.all()
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['admin'] = user.dome_moderators.all()
        context['member'] = user.dome_members.all()
        return context


def MemberRemoveView(request,dome_id, user_id):
    if request.method == 'DELETE':

        user = get_object_or_404(User, username=request.user)
        dome = get_object_or_404(Dome, pk=dome_id)
        removed = get_object_or_404(User, pk=user_id)
        if user == dome.user:
            if removed in dome.members.all():
                dome.members.remove(removed)

            elif removed in dome.moderators.all():
                dome.moderators.remove(removed)


        elif user in dome.moderators.all():
            if removed in dome.members.all():
                dome.members.remove(removed)
        return HttpResponse(f'{removed.username} has removed successfully')

@login_required
def ModeratorRaiseOrDown(request, pk, user_pk, option):
    dome = Dome.objects.get(pk=pk)
    dome_user = dome.user
    selected_user = User.objects.get(pk=user_pk)
    if request.user == dome_user:
        if int(option) == 0:
            dome.moderators.remove(selected_user)
            dome.members.add(selected_user)
            return HttpResponse('The moderator has become a member')
        elif int(option) == 1:
            dome.moderators.add(selected_user)
            dome.members.remove(selected_user)
            return HttpResponse('The member has become a moderator')
        else:
            return HttpResponseForbidden('Not allowed')
    else:
        HttpResponseForbidden('Not allowed')