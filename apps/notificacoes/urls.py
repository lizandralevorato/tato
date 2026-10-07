from django.urls import path

from . import views

app_name = "notificacoes"

urlpatterns = [
    path("notificacoes/inscrever/", views.inscrever, name="inscrever"),
    path("notificacoes/remover/", views.remover_inscricao, name="remover"),
    path("notificacoes/teste/", views.teste, name="teste"),
    path("lembrete/<str:token>/", views.lembrete, name="lembrete"),
    path("offline/", views.offline, name="offline"),
]
