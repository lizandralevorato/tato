from django.conf import settings
from django.db import models

from .vocabulario import Frequencia, Intensidade, Pressao, Regiao


class FichaSaude(models.Model):
    """Ficha de saúde de um colaborador (uma por pessoa). Dado sensível (LGPD).

    Nunca registrar este modelo no admin do Django nem em exportações com nome.
    """

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ficha_saude")
    condicoes = models.JSONField("condições de saúde", default=list, blank=True)
    condicao_outra = models.CharField("outra condição", max_length=120, blank=True)
    dor_cronica = models.BooleanField("dor crônica", default=False)
    dor_cronica_descricao = models.CharField(max_length=200, blank=True)
    problema_coluna = models.BooleanField("problema na coluna", default=False)
    problema_coluna_descricao = models.CharField(max_length=200, blank=True)
    pressao = models.CharField(
        "preferência de pressão", max_length=16, choices=Pressao.choices, default=Pressao.SEM_PREFERENCIA
    )
    evitar = models.CharField("o que o massoterapeuta deve evitar", max_length=200, blank=True)
    observacoes = models.CharField("observações gerais", max_length=500, blank=True)
    autoriza_sesmt = models.BooleanField("autoriza o SESMT a ver a ficha com o nome", default=False)
    consentimento_em = models.DateTimeField()
    consentimento_versao = models.CharField(max_length=20)
    criada_em = models.DateTimeField()
    atualizada_em = models.DateTimeField()

    class Meta:
        verbose_name = "ficha de saúde"
        verbose_name_plural = "fichas de saúde"

    def __str__(self):
        return f"Ficha de {self.usuario_id}"


class FichaRegiao(models.Model):
    ficha = models.ForeignKey(FichaSaude, on_delete=models.CASCADE, related_name="regioes")
    regiao = models.CharField(max_length=20, choices=Regiao.choices)
    intensidade = models.CharField(max_length=10, choices=Intensidade.choices, blank=True)
    frequencia = models.CharField(max_length=10, choices=Frequencia.choices, blank=True)

    class Meta:
        verbose_name = "região com dor"
        verbose_name_plural = "regiões com dor"
        constraints = [models.UniqueConstraint(fields=["ficha", "regiao"], name="uma_linha_por_regiao_na_ficha")]

    def __str__(self):
        return f"{self.regiao} ({self.ficha_id})"


class VersaoImutavel(Exception):
    """Versões do histórico não podem ser alteradas nem apagadas uma a uma."""


class FichaVersaoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise VersaoImutavel("As versões da ficha não podem ser alteradas.")

    def delete(self):
        raise VersaoImutavel("As versões da ficha só saem quando a ficha inteira é apagada.")


class FichaVersao(models.Model):
    """Cópia imutável da ficha a cada salvamento: quem, quando e o que mudou."""

    ficha = models.ForeignKey(FichaSaude, on_delete=models.CASCADE, related_name="versoes")
    numero = models.PositiveIntegerField()
    por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    em = models.DateTimeField()
    mudancas = models.JSONField(default=list)
    conteudo = models.JSONField(default=dict)

    objects = FichaVersaoQuerySet.as_manager()

    class Meta:
        verbose_name = "versão da ficha"
        verbose_name_plural = "versões da ficha"
        ordering = ["-numero"]
        constraints = [models.UniqueConstraint(fields=["ficha", "numero"], name="uma_versao_por_numero")]

    def __str__(self):
        return f"Versão {self.numero} da ficha {self.ficha_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise VersaoImutavel("As versões da ficha não podem ser alteradas.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise VersaoImutavel("As versões da ficha só saem quando a ficha inteira é apagada.")


class ApagamentoFicha(models.Model):
    """Prova de que a ficha foi apagada. Não guarda nenhum dado de saúde."""

    colaborador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    colaborador_nome = models.CharField(max_length=200)
    em = models.DateTimeField()

    class Meta:
        verbose_name = "ficha apagada"
        verbose_name_plural = "fichas apagadas"
        ordering = ["-em"]


class AcessoFicha(models.Model):
    """Quem consultou a ficha de quem, e quando. Visível ao SESMT e a cada colaborador (a própria)."""

    class Finalidade(models.TextChoices):
        ATENDIMENTO = "atendimento", "Massoterapeuta abriu a ficha do atendimento"
        SESMT_FICHA = "sesmt_ficha", "SESMT abriu a ficha"
        SESMT_AGREGADO = "sesmt_agregado", "SESMT baixou a planilha agregada"
        SESMT_PLANILHA = "sesmt_planilha", "SESMT baixou a planilha com nomes"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    usuario_nome = models.CharField(max_length=200)
    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="acessos_a_ficha"
    )
    colaborador_nome = models.CharField(max_length=200, blank=True)
    agendamento = models.ForeignKey("agenda.Agendamento", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    finalidade = models.CharField(max_length=20, choices=Finalidade.choices)
    em = models.DateTimeField()

    class Meta:
        verbose_name = "acesso à ficha"
        verbose_name_plural = "acessos à ficha"
        ordering = ["-em", "-pk"]
        indexes = [models.Index(fields=["em"])]

    def __str__(self):
        return f"{self.usuario_nome} → {self.colaborador_nome} em {self.em:%d/%m %H:%M}"


class SugestaoDispensada(models.Model):
    """A pessoa disse "Agora não" para a sugestão de pôr a região na ficha."""

    colaborador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    regiao = models.CharField(max_length=20, choices=Regiao.choices)
    em = models.DateTimeField()

    class Meta:
        ordering = ["-em"]
        indexes = [models.Index(fields=["colaborador", "regiao"])]


class ConviteFicha(models.Model):
    """Quando o convite (e o lembrete de ficha desatualizada) já apareceu, para não insistir."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="convite_ficha")
    convite_em = models.DateTimeField(null=True, blank=True)
    lembrete_em = models.DateTimeField(null=True, blank=True)
