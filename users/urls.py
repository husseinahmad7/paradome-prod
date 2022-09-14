from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'users'
urlpatterns = [
    path('', views.index ,name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='users/login.html'), name='login'),
    
    # path('login/', views.login_page, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', auth_views.LogoutView.as_view(template_name='users/logout.html'), name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('usersearch/', views.UserSearch , name='user_search'),

    # confirm password reset is in the project urls.py    
]