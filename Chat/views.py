from django.http import HttpResponseRedirect, HttpResponse
from django.http.response import Http404
from django.urls import reverse
from django.views import generic
from django.contrib.auth.mixins import LoginRequiredMixin,UserPassesTestMixin
from .models import ChatChannel, ChatMessage
from .forms import ChatMessageCreation,ChatChannelCreation
from Domes.models import Category,Dome
# streming
import time
from django.http import StreamingHttpResponse

class ChatMessageList(LoginRequiredMixin, generic.ListView,generic.edit.FormMixin):
    template_name = 'Chat/chat_messages.html'
    model = ChatMessage
    context_object_name = 'messages'
    paginate = 10
    form_class = ChatMessageCreation

    def get_channel_obj(self, pk):
        try:
            return ChatChannel.objects.get(pk=pk)
        except ChatChannel.DoesNotExist:
            raise Http404
    def get_context_data(self, **kwargs):
        context = super(ChatMessageList,self).get_context_data(**kwargs)
        channel = self.get_channel_obj(self.kwargs.get('pk'))
        messages = ChatMessage.objects.filter(channel=channel).order_by('date')
        # form = self.get_form()
        channel_id = channel.id
        category = channel.category
        dome = Dome.objects.get(pk=category.Dome.id)
        moderators = dome.moderators.all()
        dome_owner = dome.user
        context['dome_owner'] = dome_owner
        context['channel_id'] = channel_id
        context['messages'] = messages
        context['moderators'] = moderators
        # context['form']= form
        return context

    def post(self, request, *args, **kwargs):
        form = ChatMessageCreation(self.request.POST, self.request.FILES)
        if form.is_valid():
            body = form.cleaned_data.get('body')
            file = form.cleaned_data.get('file')
            sender = self.request.user
            channel= self.get_channel_obj(self.kwargs.get('pk'))

            m, created = ChatMessage.objects.get_or_create(user=sender, body=body, file=file, channel=channel)
            m.save()
            if 'HX-Request' in self.request.headers.keys() and self.request.headers.get('HX-Request') == 'true':
                return HttpResponse(status=204)
            return HttpResponseRedirect(reverse('chat:chat-channel',args=[channel.id]))

class ChatChannelCreateView(LoginRequiredMixin, generic.DetailView, generic.edit.FormMixin):
    model = Category
    template_name = 'Chat/chatchannel_form.html'
    form_class = ChatChannelCreation
    def post(self, *args, **kwargs):
         form = ChatChannelCreation(self.request.POST)
         if form.is_valid():
             chtchnl_category = self.get_object()
             title = form.cleaned_data['title']
             topic = form.cleaned_data['topic']
             chatchannel = ChatChannel(title=title,topic=topic,category= chtchnl_category)
             chatchannel.save()
             return HttpResponseRedirect(reverse('domes:dome-detail', args=[chtchnl_category.Dome.id]))

class ChatMessageDeleteView(LoginRequiredMixin, generic.DeleteView, UserPassesTestMixin):
    model = ChatMessage
    # success_url = ''

    def test_func(self):
        message = self.get_object()
        if self.request.user == message.user:
            return True
        return False

    def get_success_url(self) -> str:
        return reverse('chat:msg-deleted')

def msgDeleted(request):
    return HttpResponse('<article class="message"><div class="message-body">Message has been deleted</div></article>')

# @login_required
def stream(request, chat_pk):
    def event_stream():
        id = 1
        while True:
            channel = ChatChannel.objects.get(pk=chat_pk)
            msgs = ChatMessage.objects.filter(channel=channel, is_read=False)

            if msgs.exists():
                    for msg in msgs:
                        yield f'event:new_msg\ndata:\nid:{id}\n\n'
                        id = id +1
            time.sleep(3)

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')

class getNewMsgsView(LoginRequiredMixin, generic.DetailView):
    template_name = 'Chat/requested_msgs.html'
    context_object_name = 'object'

    def get_channel_obj(self, pk):
        try:
            return ChatChannel.objects.get(pk=pk)
        except ChatChannel.DoesNotExist:
            raise Http404
    def get_object(self, *args, **kwargs):
        channel = self.get_channel_obj(self.kwargs.get('chat_pk'))
        msg = ChatMessage.objects.filter(channel=channel, is_read=False).earliest('date')
        return msg

    def get(self,request, *args, **kwargs):
        obj = self.get_object()
        channel = self.get_channel_obj(self.kwargs.get('chat_pk'))
        category = channel.category
        dome = Dome.objects.get(pk=category.Dome.id)
        moderators = dome.moderators.all()
        dome_owner = dome.user
        context = {}
        context['dome_owner'] = dome_owner
        context['moderators'] = moderators
        time.sleep(1)

        obj.is_read = True
        obj.save()
        context['object'] = obj

        return self.render_to_response(context)

    # def get_context_data(self, **kwargs):
    #     context = super(getNewMsgsView,self).get_context_data(**kwargs)
    #     channel = self.get_channel_obj(self.kwargs.get('pk'))
    #     category = channel.category
    #     dome = Dome.objects.get(pk=category.Dome.id)
    #     moderators = dome.moderators.all()
    #     dome_owner = dome.user
    #     context['dome_owner'] = dome_owner
    #     context['moderators'] = moderators
    #     return context
