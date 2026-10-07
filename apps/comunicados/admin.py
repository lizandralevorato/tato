from django.contrib import admin

from .models import Comunicado


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "publico", "unidade", "ativo", "publicado_em"]
    list_filter = ["publico", "unidade", "ativo"]
    search_fields = ["titulo", "texto"]
