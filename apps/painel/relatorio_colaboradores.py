"""Atividade de cada colaborador no período: reservas, check-ins, faltas e encaixes."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.agenda.models import Agendamento

from . import indicadores

Status = Agendamento.Status


@dataclass
class Atividade:
    colaborador: object
    contagem: Counter = field(default_factory=Counter)
    checkins: int = 0
    chegadas: int = 0
    encaixes: int = 0
    encaixes_em_vaga_liberada: int = 0
    por_mes: dict = field(default_factory=dict)  # (ano, mês) -> Counter de status

    @property
    def total(self):
        return sum(self.contagem.values())

    @property
    def cancelados(self):
        return self.contagem[Status.CANCELADO]

    @property
    def liberados(self):
        return self.contagem[Status.EXPIRADO]

    @property
    def reservados(self):
        return self.total - self.cancelados - self.liberados

    @property
    def realizados(self):
        return self.contagem[Status.REALIZADO]

    @property
    def faltas(self):
        return self.contagem[Status.FALTA]

    @property
    def taxa_faltas(self):
        return indicadores._porcentagem(self.faltas, self.realizados + self.faltas)

    @property
    def taxa_checkin(self):
        return indicadores._porcentagem(self.checkins, self.reservados)

    def somar(self, ag):
        self.contagem[ag.status] += 1
        mes = timezone.localtime(ag.inicio)
        self.por_mes.setdefault((mes.year, mes.month), Counter())[ag.status] += 1
        if ag.confirmado_em:
            self.checkins += 1
        if ag.chegada_em:
            self.chegadas += 1
        if ag.origem == Agendamento.Origem.ENCAIXE:
            self.encaixes += 1
            if ag.em_vaga_liberada:
                self.encaixes_em_vaga_liberada += 1


def reservas(unidade, de: date, ate: date, massoterapeuta=None):
    """Agendamentos do período, marcando os encaixes que ocuparam uma vaga liberada por falta de check-in."""
    liberada = Agendamento.objects.filter(
        massoterapeuta=OuterRef("massoterapeuta"), inicio=OuterRef("inicio"), status=Status.EXPIRADO
    ).exclude(pk=OuterRef("pk"))
    qs = (
        indicadores.agendamentos(unidade, de, ate, massoterapeuta)
        .annotate(em_vaga_liberada=Exists(liberada))
        .select_related("colaborador", "massoterapeuta__usuario", "cancelado_por")
    )
    return qs.order_by("inicio")


def atividade_por_colaborador(agendamentos):
    por_pessoa = {}
    for ag in agendamentos:
        por_pessoa.setdefault(ag.colaborador_id, Atividade(ag.colaborador)).somar(ag)
    return sorted(por_pessoa.values(), key=lambda a: a.colaborador.nome.casefold())
