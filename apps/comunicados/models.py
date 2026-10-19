from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class ComunicadoQuerySet(models.QuerySet):
    def para(self, usuario):
        """Comunicados publicados, dentro do período de exibição, que essa pessoa deve ver."""
        hoje = timezone.localdate()
        qs = self.filter(ativo=True).filter(
            Q(data_inicio__isnull=True) | Q(data_inicio__lte=hoje),
            Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
        )
        if usuario.unidade_id:
            qs = qs.filter(Q(unidade__isnull=True) | Q(unidade_id=usuario.unidade_id))
        if usuario.eh_massoterapeuta or usuario.eh_equipe:
            return qs
        return qs.filter(publico=Comunicado.Publico.TODOS)

    def nao_lidos_por(self, usuario):
        return self.para(usuario).exclude(leituras__usuario=usuario)


class Comunicado(models.Model):
    class Publico(models.TextChoices):
        MASSOTERAPEUTAS = "massoterapeutas", "Só massoterapeutas"
        TODOS = "todos", "Todas as pessoas (colaboradores também)"

    class Nivel(models.TextChoices):
        INFORMATIVO = "informativo", "Informativo"
        IMPORTANTE = "importante", "Importante"
        URGENTE = "urgente", "Urgente"
        EVENTO = "evento", "Evento"

    titulo = models.CharField("título", max_length=120)
    texto = models.TextField()
    nivel = models.CharField("nível", max_length=16, choices=Nivel.choices, default=Nivel.INFORMATIVO, blank=True)
    publico = models.CharField("para quem", max_length=16, choices=Publico.choices, default=Publico.MASSOTERAPEUTAS)
    unidade = models.ForeignKey(
        "agenda.Unidade",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comunicados",
        help_text="Deixe em branco para todas as unidades.",
    )
    data_inicio = models.DateField(
        "exibir a partir de", null=True, blank=True, help_text="Deixe em branco para exibir desde já."
    )
    data_fim = models.DateField(
        "exibir até", null=True, blank=True, help_text="Deixe em branco para exibir para sempre."
    )
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    ativo = models.BooleanField("publicado", default=True)
    publicado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    objects = ComunicadoQuerySet.as_manager()

    class Meta:
        ordering = ["-publicado_em"]

    def __str__(self):
        return self.titulo


class LeituraComunicado(models.Model):
    comunicado = models.ForeignKey(Comunicado, on_delete=models.CASCADE, related_name="leituras")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    lido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "leitura de comunicado"
        verbose_name_plural = "leituras de comunicados"
        constraints = [models.UniqueConstraint(fields=["comunicado", "usuario"], name="uma_leitura_por_pessoa")]
