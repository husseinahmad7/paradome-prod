
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from Domes.sitemap import DomesSitemap
from posts.sitemap import PostsSitemap
from django.contrib.sitemaps.views import sitemap
sitemaps = {
    'dome': DomesSitemap,
    'post': PostsSitemap,
}
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('HusseinAh.urls')),
    path('users/', include('users.urls')),
    path('posts/', include('posts.urls')),
    path('messages/', include('messages.urls')),
    path('notifications/', include('notify.urls')),
    # path('api/', include('apiapp.urls')),
    # path('api_auth/', include('rest_framework.urls')),
    # path('store/', include('store.urls')),
    path('dome/', include('Domes.urls')),
    path('chat/', include('Chat.urls')),


    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='users/password_reset.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'), name='password_reset_complete'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

