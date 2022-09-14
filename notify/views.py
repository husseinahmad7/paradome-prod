from django.shortcuts import render, redirect
from notify.models import Notification
# Create your views here.
def showNotification(request):
    user = request.user
    notifications = Notification.objects.filter(user=user).order_by('-date')
    
    context = {'notifications': notifications}
    return render(request, 'notify/notifications.html', context)

def deleteNotification(request, notify_pk):
    user = request.user
    Notification.objects.filter(pk=notify_pk, user=user).delete()
    return redirect('notify:notification')

def CountNotifications(request):
    notify_count = 0
    if request.user.is_authenticated:
        notify_count = Notification.objects.filter(user=request.user, is_seen=False).count()
    
    return {'notify_count': notify_count}