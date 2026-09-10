from django.urls import path
from . import views

app_name = 'chat'
urlpatterns = [
    path('<int:pk>/', views.ChatMessageList.as_view(), name='chat-channel'),
    path('<int:pk>/new', views.ChatChannelCreateView.as_view(), name='chatchannel-create'),
    path('chatmsg/<int:pk>', views.delete_message, name='msg-delete'),
    path('pusher/auth/', views.pusher_auth, name='pusher-auth'),
    path(
        'channels/<int:channel_pk>/messages/<int:pk>/fragment/',
        views.message_fragment,
        name='message-fragment',
    ),
    # path('stream/<int:chat_pk>/', views.stream, name='event-stream'),
    # path('getmsgs/<int:chat_pk>/', views.getNewMsgsView.as_view(), name='new_msgs_htmx'),
    
    
]
