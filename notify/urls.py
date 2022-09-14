from django.urls import path
from notify.views import showNotification, deleteNotification
app_name = 'notify'
urlpatterns = [
    path('', showNotification, name='notification' ),
    path('del/<int:notify_pk>', deleteNotification, name='del' ),
]