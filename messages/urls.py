from django.urls import path
from messages import views


app_name = 'messages'
urlpatterns = [
    path('inbox', views.inbox , name='inbox'),
    path('msg/<str:username>/', views.directs , name='directs'),
    
    
]