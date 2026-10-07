from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from apps.agenda.views import inicio
from apps.agenda.views.paginas import como_funciona
from apps.notificacoes.views import service_worker

admin.site.site_header = "Agenda de Massagem: administração"
admin.site.site_title = "Agenda de Massagem"
admin.site.index_title = "Cadastros"

urlpatterns = [
    path("", inicio, name="inicio"),
    # Na raiz para o service worker controlar o site inteiro (escopo "/").
    path("sw.js", service_worker, name="service_worker"),
    path(
        "acessibilidade/",
        TemplateView.as_view(template_name="acessibilidade.html"),
        name="acessibilidade",
    ),
    path("como-funciona/", como_funciona, name="como_funciona"),
    path("", include("apps.contas.urls")),
    path("", include("apps.agenda.urls")),
    path("", include("apps.notificacoes.urls")),
    path("", include("apps.comunicados.urls")),
    path("", include("apps.painel.urls")),
    path("admin/", admin.site.urls),
]
