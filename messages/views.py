from django.core import paginator
from django.http.response import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse
from messages.models import Message
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.http import HttpResponse

@login_required
def inbox(request):
    user = request.user
    messages =Message.get_messages(user=user)
    active_direct = None
    directs = None
    context = {}
    if messages:
        message = messages[0]
        active_direct = message['user'].username
        directs = Message.objects.filter(user=user, recipient=message['user'])
        directs.update(is_read=True)
        
        for message in messages:
            if message['user'].username == active_direct:
                message['unread']=0

        context = {'directs': directs, 'messages': messages, 'active_direct': active_direct}
    return render(request, 'messages/inbox.html', context)
        

@login_required
def directs(request, username):
    user = request.user
    messages = Message.get_messages(user=user)
    active_direct = username
    directs = Message.objects.filter(user=user, recipient__username=username)
    directs.update(is_read=True)
    
    for message in messages:
        if message['user'].username == username:
            message['unread'] = 0
    if request.method == "POST":
        from_user = request.user
        to_user_un = request.POST['to_user']
        body = request.POST['body']
        to_user = get_object_or_404(User, username=to_user_un)
        Message.send_message(from_user=from_user, to_user=to_user,body=body)
        return HttpResponseRedirect(reverse('messages:directs', args=[active_direct]))
    context= {'directs': directs, 'messages': messages, 'active_direct':active_direct}
    return render(request, 'messages/inbox.html', context)

def check_directs(request):
    unread_count = 0
    if request.user.is_authenticated:
        unread_count = Message.objects.filter(user=request.user, is_read=False).count()
    return {'unread_count': unread_count}