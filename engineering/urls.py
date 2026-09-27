from django.urls import path
from . import views

app_name = "engineering"
urlpatterns = [
    path("", views.index, name="index"),
    path("runs/", views.create_run, name="create_run"),
    path("runs/<uuid:run_id>/", views.run_detail, name="run_detail"),
    path("runs/<uuid:run_id>/submit/", views.submit, name="submit"),
    path("runs/<uuid:run_id>/delivery/", views.delivery, name="delivery"),
    path("runs/<uuid:run_id>/reset/", views.reset, name="reset"),
    path("permissions/", views.permissions, name="permissions"),
]
