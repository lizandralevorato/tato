from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Unidade(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class PoliticaBeneficio(models.Model):
    """Regras do benefício. A recepção e a gestão alteram pela tela Regras do benefício."""

    unidade = models.OneToOneField(Unidade, on_delete=models.CASCADE, related_name="politica")
    max_por_semana = models.PositiveSmallIntegerField("máximo de massagens por semana", default=2)
    uma_por_dia = models.BooleanField("no máximo uma por dia", default=True)
    falta_conta_no_limite = models.BooleanField("falta conta no limite semanal", default=True)
    tolerancia_min = models.PositiveSmallIntegerField("tolerância de atraso (min)", default=5)
    antecedencia_cancelamento_min = models.PositiveSmallIntegerField(
        "cancelamento até quantos minutos antes", default=15
    )
    checkin_abre_min = models.PositiveSmallIntegerField(
        "check-in abre quantos minutos antes (o lembrete sai nesse momento)", default=120
    )
    checkin_prazo_min = models.PositiveSmallIntegerField(
        "prazo do check-in: até quantos minutos antes (0 = check-in não obrigatório)", default=60
    )
    checkin_tolerancia_min = models.PositiveSmallIntegerField(
        "tolerância depois do prazo do check-in (min)", default=5
    )
    chegada_abre_min = models.PositiveSmallIntegerField(
        "botão 'Cheguei' liberado quantos minutos antes", default=10
    )
    dias_para_agendar = models.PositiveSmallIntegerField(
        "agendamento com até quantos dias de antecedência", default=14
    )
    aviso_proximo_min = models.PositiveSmallIntegerField(
        "avisar o massoterapeuta quantos minutos antes (0 = desligado)", default=5
    )

    class Meta:
        verbose_name = "política do benefício"
        verbose_name_plural = "políticas do benefício"

    def __str__(self):
        return f"Política de {self.unidade}"


class Massoterapeuta(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="massoterapeuta",
        limit_choices_to={"papel": "massoterapeuta"},
    )
    unidade = models.ForeignKey(Unidade, on_delete=models.PROTECT, related_name="massoterapeutas")
    duracao_sessao_min = models.PositiveSmallIntegerField("duração da sessão (min)", default=20)
    intervalo_min = models.PositiveSmallIntegerField("intervalo entre sessões (min)", default=20)
    ativo = models.BooleanField("atendendo", default=True)

    class Meta:
        ordering = ["usuario__first_name"]

    def __str__(self):
        return self.nome

    def clean(self):
        if self.usuario_id and not self.usuario.eh_massoterapeuta:
            raise ValidationError(
                {"usuario": "Só usuários com o papel Massoterapeuta podem atender. Mude o papel da pessoa antes."}
            )

    @property
    def nome(self):
        return self.usuario.nome


class Disponibilidade(models.Model):
    """Período semanal recorrente em que o massoterapeuta atende."""

    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, "Segunda-feira"
        TERCA = 1, "Terça-feira"
        QUARTA = 2, "Quarta-feira"
        QUINTA = 3, "Quinta-feira"
        SEXTA = 4, "Sexta-feira"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    massoterapeuta = models.ForeignKey(
        Massoterapeuta, on_delete=models.CASCADE, related_name="disponibilidades"
    )
    dia_semana = models.PositiveSmallIntegerField("dia da semana", choices=DiaSemana.choices)
    hora_inicio = models.TimeField("começa às")
    hora_fim = models.TimeField("termina às")

    class Meta:
        ordering = ["dia_semana", "hora_inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_fim__gt=models.F("hora_inicio")),
                name="disponibilidade_fim_depois_do_inicio",
            )
        ]

    def __str__(self):
        return f"{self.massoterapeuta}, {self.get_dia_semana_display()} {self.hora_inicio:%H:%M} a {self.hora_fim:%H:%M}"


class Bloqueio(models.Model):
    """Período em que o massoterapeuta não atende (folga, férias, pausa rápida)."""

    class Motivo(models.TextChoices):
        PAUSA = "pausa", "Pausa rápida"
        FOLGA = "folga", "Folga"
        FERIAS = "ferias", "Férias"
        OUTRO = "outro", "Outro"

    massoterapeuta = models.ForeignKey(Massoterapeuta, on_delete=models.CASCADE, related_name="bloqueios")
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    motivo = models.CharField(max_length=10, choices=Motivo.choices, default=Motivo.OUTRO)
    observacao = models.CharField("observação", max_length=200, blank=True)

    class Meta:
        ordering = ["-inicio"]

    def clean(self):
        if self.inicio and self.fim and self.fim <= self.inicio:
            raise ValidationError("O fim precisa ser depois do início.")

    def __str__(self):
        return f"{self.massoterapeuta}: {self.get_motivo_display()}"


class AgendamentoQuerySet(models.QuerySet):
    def ativos(self):
        """Agendamentos que ocupam o horário (tudo, menos cancelados e liberados)."""
        return self.exclude(status__in=Agendamento.LIBERAM_HORARIO)


class Agendamento(models.Model):
    class Status(models.TextChoices):
        AGENDADO = "agendado", "Agendado"
        CONFIRMADO = "confirmado", "Check-in feito"
        CHEGOU = "chegou", "Chegou"
        REALIZADO = "realizado", "Atendido"
        FALTA = "falta", "Faltou"
        CANCELADO = "cancelado", "Cancelado"
        EXPIRADO = "expirado", "Liberado (sem check-in)"

    class Origem(models.TextChoices):
        AUTOAGENDAMENTO = "autoagendamento", "Pelo próprio colaborador"
        RECEPCAO = "recepcao", "Pela recepção"
        ENCAIXE = "encaixe", "Encaixe"

    PENDENTES = {Status.AGENDADO, Status.CONFIRMADO}
    EM_ABERTO = {Status.AGENDADO, Status.CONFIRMADO, Status.CHEGOU}
    LIBERAM_HORARIO = [Status.CANCELADO, Status.EXPIRADO]

    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="agendamentos",
        limit_choices_to=~Q(papel="massoterapeuta"),
    )
    massoterapeuta = models.ForeignKey(Massoterapeuta, on_delete=models.PROTECT, related_name="agendamentos")
    inicio = models.DateTimeField()
    fim = models.DateTimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AGENDADO)
    origem = models.CharField(max_length=16, choices=Origem.choices, default=Origem.AUTOAGENDAMENTO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    confirmado_em = models.DateTimeField("check-in feito em", null=True, blank=True)
    chegada_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = AgendamentoQuerySet.as_manager()

    class Meta:
        ordering = ["inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["massoterapeuta", "inicio"],
                condition=~Q(status__in=["cancelado", "expirado"]),
                name="um_agendamento_ativo_por_horario",
            ),
        ]
        indexes = [models.Index(fields=["colaborador", "inicio"])]

    def clean(self):
        if self.colaborador_id and self.colaborador.eh_massoterapeuta:
            raise ValidationError({"colaborador": "Massoterapeutas não podem agendar massagem."})

    def __str__(self):
        return f"{self.colaborador} com {self.massoterapeuta} em {self.inicio:%d/%m %H:%M}"


class HistoricoAgendamento(models.Model):
    """Cada mudança de um agendamento: o que aconteceu, quando e quem fez."""

    class Acao(models.TextChoices):
        AGENDADO = "agendado", "Agendou"
        AGENDADO_EQUIPE = "agendado_equipe", "Agendou pela recepção"
        ENCAIXE = "encaixe", "Encaixou"
        CHECKIN = "checkin", "Fez check-in"
        CHEGADA = "chegada", "Avisou a chegada"
        REALIZADO = "realizado", "Marcou como atendido"
        FALTA = "falta", "Marcou falta"
        CANCELADO = "cancelado", "Cancelou"
        LIBERADO = "liberado", "Liberou (sem check-in)"

    agendamento = models.ForeignKey(Agendamento, on_delete=models.CASCADE, related_name="historico")
    acao = models.CharField(max_length=20, choices=Acao.choices)
    por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    detalhe = models.CharField(max_length=300, blank=True)
    em = models.DateTimeField()

    class Meta:
        verbose_name = "histórico de agendamento"
        verbose_name_plural = "histórico de agendamentos"
        ordering = ["-em", "-pk"]
        indexes = [models.Index(fields=["em"])]

    def __str__(self):
        return f"{self.get_acao_display()}: {self.agendamento}"

    @property
    def quem(self):
        return self.por.nome if self.por else "Sistema"


class ListaEspera(models.Model):
    """Pedido de "me avise se abrir vaga" para um dia, com um massoterapeuta ou qualquer um."""

    colaborador = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lista_espera"
    )
    unidade = models.ForeignKey(Unidade, on_delete=models.CASCADE, related_name="lista_espera")
    dia = models.DateField()
    massoterapeuta = models.ForeignKey(
        Massoterapeuta, on_delete=models.CASCADE, null=True, blank=True, related_name="lista_espera"
    )
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    avisado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "pedido na lista de espera"
        verbose_name_plural = "lista de espera"
        ordering = ["dia", "criada_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["colaborador", "dia"],
                condition=Q(ativa=True),
                name="uma_espera_ativa_por_dia",
            )
        ]

    def __str__(self):
        return f"{self.colaborador} espera vaga em {self.dia:%d/%m}"
