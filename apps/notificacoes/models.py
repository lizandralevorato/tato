from django.conf import settings
from django.db import models
from django.db.models import Q


class InscricaoPush(models.Model):
    """Um aparelho (navegador) que aceitou receber notificações."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inscricoes_push"
    )
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    aparelho = models.CharField(max_length=200, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    ultimo_envio_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "aparelho inscrito"
        verbose_name_plural = "aparelhos inscritos"

    def __str__(self):
        return f"{self.usuario}: {self.aparelho or 'aparelho'}"

    @property
    def como_dict(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}


class Notificacao(models.Model):
    """Histórico de cada aviso. Também evita mandar o mesmo lembrete duas vezes."""

    class Tipo(models.TextChoices):
        LEMBRETE = "lembrete", "Lembrete de check-in"
        ULTIMO_AVISO = "ultimo_aviso", "Último aviso de check-in"
        LIBERADO = "liberado", "Reserva liberada (sem check-in)"
        NOVO_AGENDAMENTO = "novo", "Novo agendamento"
        CHEGADA = "chegada", "Chegada"
        CANCELAMENTO = "cancelamento", "Cancelamento"
        PROXIMO = "proximo", "Próximo atendimento"
        VAGA = "vaga", "Vaga aberta (lista de espera)"
        COMUNICADO = "comunicado", "Comunicado"
        TESTE = "teste", "Teste"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificacoes")
    agendamento = models.ForeignKey(
        "agenda.Agendamento", on_delete=models.CASCADE, null=True, blank=True, related_name="notificacoes"
    )
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    titulo = models.CharField(max_length=120)
    corpo = models.CharField(max_length=300)
    url = models.CharField(max_length=300, default="/")
    urgente = models.BooleanField(default=False)
    validade_seg = models.PositiveIntegerField(default=3600)
    criada_em = models.DateTimeField(auto_now_add=True)
    enviada_em = models.DateTimeField(null=True, blank=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    erro = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        ordering = ["-criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "agendamento", "tipo"],
                condition=Q(agendamento__isnull=False),
                name="uma_notificacao_por_tipo_e_agendamento",
            )
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} para {self.usuario}"
