from django.urls import path

from . import views

app_name = "painel"

urlpatterns = [
    path("painel/", views.inicio, name="inicio"),
    path("painel/agendamentos.csv", views.csv_agendamentos, name="csv_agendamentos"),
    path("painel/resumo.csv", views.csv_resumo, name="csv_resumo"),
    path("painel/agendamentos.xlsx", views.xlsx_agendamentos, name="xlsx_agendamentos"),
    path("painel/resumo.xlsx", views.xlsx_resumo, name="xlsx_resumo"),
    path("painel/historico/", views.historico, name="historico"),
]
