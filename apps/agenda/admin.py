from django.contrib import admin

from .models import (
    Agendamento,
    Bloqueio,
    Disponibilidade,
    HistoricoAgendamento,
    ListaEspera,
    Massoterapeuta,
    PoliticaBeneficio,
    Unidade,
)


class PoliticaInline(admin.StackedInline):
    model = PoliticaBeneficio
    can_delete = False


@admin.register(Unidade)
class UnidadeAdmin(admin.ModelAdmin):
    list_display = ["nome", "ativa"]
    inlines = [PoliticaInline]


class DisponibilidadeInline(admin.TabularInline):
    model = Disponibilidade
    extra = 1


@admin.register(Massoterapeuta)
class MassoterapeutaAdmin(admin.ModelAdmin):
    list_display = ["nome", "unidade", "duracao_sessao_min", "intervalo_min", "ativo"]
    list_filter = ["unidade", "ativo"]
    inlines = [DisponibilidadeInline]
    autocomplete_fields = ["usuario"]


@admin.register(Bloqueio)
class BloqueioAdmin(admin.ModelAdmin):
    list_display = ["massoterapeuta", "motivo", "inicio", "fim"]
    list_filter = ["motivo", "massoterapeuta"]
    date_hierarchy = "inicio"


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ["inicio", "massoterapeuta", "colaborador", "status", "origem"]
    list_filter = ["status", "origem", "massoterapeuta"]
    search_fields = ["colaborador__email", "colaborador__first_name", "colaborador__last_name"]
    date_hierarchy = "inicio"
    autocomplete_fields = ["colaborador"]
    readonly_fields = ["criado_em", "atualizado_em", "confirmado_em", "chegada_em", "cancelado_em", "cancelado_por"]


@admin.register(HistoricoAgendamento)
class HistoricoAgendamentoAdmin(admin.ModelAdmin):
    list_display = ["em", "acao", "por", "agendamento", "detalhe"]
    list_filter = ["acao"]
    date_hierarchy = "em"
    readonly_fields = [f.name for f in HistoricoAgendamento._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ListaEspera)
class ListaEsperaAdmin(admin.ModelAdmin):
    list_display = ["dia", "colaborador", "massoterapeuta", "ativa", "avisado_em"]
    list_filter = ["ativa", "unidade"]
    date_hierarchy = "dia"
