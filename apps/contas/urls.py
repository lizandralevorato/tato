from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "contas"

urlpatterns = [
    path("entrar/", views.EntrarView.as_view(), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),
    path("preferencias/", views.preferencias, name="preferencias"),
]
