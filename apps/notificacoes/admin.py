from django.contrib import admin

from .models import InscricaoPush, Notificacao


@admin.register(Notificacao)
class NotificacaoAdmin(admin.ModelAdmin):
    list_display = ["criada_em", "tipo", "usuario", "titulo", "enviada_em", "tentativas", "erro"]
    list_filter = ["tipo", ("enviada_em", admin.EmptyFieldListFilter)]
    search_fields = ["usuario__email", "usuario__first_name", "corpo"]
    date_hierarchy = "criada_em"
    readonly_fields = [f.name for f in Notificacao._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(InscricaoPush)
class InscricaoPushAdmin(admin.ModelAdmin):
    list_display = ["usuario", "aparelho", "criada_em", "ultimo_envio_em"]
    search_fields = ["usuario__email"]
    readonly_fields = ["usuario", "endpoint", "p256dh", "auth", "aparelho", "criada_em", "ultimo_envio_em"]
