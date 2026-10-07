from django.conf import settings
from django.db import models
from django.db.models import Q


class ComunicadoQuerySet(models.QuerySet):
    def para(self, usuario):
        """Comunicados publicados que essa pessoa deve ver."""
        qs = self.filter(ativo=True)
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

    titulo = models.CharField("título", max_length=120)
    texto = models.TextField()
    publico = models.CharField("para quem", max_length=16, choices=Publico.choices, default=Publico.MASSOTERAPEUTAS)
    unidade = models.ForeignKey(
        "agenda.Unidade",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comunicados",
        help_text="Deixe em branco para todas as unidades.",
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
