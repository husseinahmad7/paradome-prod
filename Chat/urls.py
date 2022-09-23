from urllib import request
from django.urls import path
from . import views
from django.template.response import TemplateResponse

app_name = 'chat'
urlpatterns = [
    path('<int:pk>/', views.ChatMessageList.as_view(), name='chat-channel'),
    path('<int:pk>/new', views.ChatChannelCreateView.as_view(), name='chatchannel-create'),
    path('chatmsg/<int:pk>', views.ChatMessageDeleteView.as_view(), name='msg-delete'),
    path('chatmsg/deleted', views.msgDeleted, name='msg-deleted'),
    # path('stream/<int:chat_pk>/', views.stream, name='event-stream'),
    # path('getmsgs/<int:chat_pk>/', views.getNewMsgsView.as_view(), name='new_msgs_htmx'),
    
    
]