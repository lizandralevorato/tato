from django.urls import path

from . import saude, views

app_name = "painel"

urlpatterns = [
    path("painel/saude/", saude.saude, name="saude"),
    path("painel/saude/fichas/", saude.fichas, name="saude_fichas"),
    path("painel/saude/pessoas/<int:pk>/", saude.ficha_da_pessoa, name="saude_pessoa"),
    path("painel/saude/acessos/", saude.acessos, name="saude_acessos"),
    path("painel/saude/agregado.csv", saude.csv_agregado, name="saude_csv"),
    path("painel/saude/agregado.xlsx", saude.xlsx_agregado, name="saude_agregado_xlsx"),
    path("painel/saude/fichas.xlsx", saude.xlsx_fichas, name="saude_xlsx"),
    path("painel/", views.inicio, name="inicio"),
    path("painel/agendamentos.csv", views.csv_agendamentos, name="csv_agendamentos"),
    path("painel/resumo.csv", views.csv_resumo, name="csv_resumo"),
    path("painel/agendamentos.xlsx", views.xlsx_agendamentos, name="xlsx_agendamentos"),
    path("painel/resumo.xlsx", views.xlsx_resumo, name="xlsx_resumo"),
    path("painel/historico/", views.historico, name="historico"),
]
