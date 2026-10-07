from django.urls import path

from . import views

app_name = "comunicados"

urlpatterns = [
    path("comunicados/", views.lista, name="lista"),
    path("comunicados/gerenciar/", views.gerenciar, name="gerenciar"),
    path("comunicados/novo/", views.editar, name="novo"),
    path("comunicados/<int:pk>/editar/", views.editar, name="editar"),
    path("comunicados/<int:pk>/excluir/", views.excluir, name="excluir"),
]
