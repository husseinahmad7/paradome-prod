from django.urls import path
from . import views


app_name = 'domes'
urlpatterns = [
    path('', views.ExploreDomesView.as_view(),name='explore'),
    path('new/', views.DomeCreateView.as_view(),name='dome-create'),
    path('update/<int:pk>', views.DomeUpdateView.as_view(),name='dome-update'),
    path('delete/<int:pk>', views.DomeDeleteView.as_view(),name='dome-delete'),
    path('<int:pk>/',views.DomeView.as_view(),name='dome-detail'),
    path('<int:pk>/members',views.DomeMembersView.as_view(),name='dome-members'),
    path('<int:dome_id>/members/<int:user_id>/del',views.MemberRemoveView,name='dome-member-delete'),
    path('<int:pk>/info',views.DomeViewHtmx.as_view(),name='dome-info'),
    path('<int:pk>/newcategory/',views.CategoryCreateView.as_view(),name='category-create'),
    path('<str:slug>/<str:code>', views.DomeInvitationView.as_view(),name='dome-invitation'),
    path('mine/', views.UserDomesView.as_view(), name='user-domes')
]