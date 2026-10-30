"""Números do painel do SESMT, calculados a partir dos agendamentos."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.formatacao import inicio_da_semana
from apps.agenda.models import Agendamento, Massoterapeuta

Status = Agendamento.Status


def limites(de: date, ate: date):
    inicio = timezone.make_aware(datetime.combine(de, time.min))
    fim = timezone.make_aware(datetime.combine(ate + timedelta(days=1), time.min))
    return inicio, fim


def agendamentos(unidade, de: date, ate: date, massoterapeuta=None):
    inicio, fim = limites(de, ate)
    qs = Agendamento.objects.filter(massoterapeuta__unidade=unidade, inicio__gte=inicio, inicio__lt=fim)
    if massoterapeuta is not None:
        qs = qs.filter(massoterapeuta=massoterapeuta)
    return qs


def _porcentagem(parte, todo):
    return round(100 * parte / todo) if todo else None


@dataclass
class Linha:
    rotulo: str
    oferecidos: int = 0
    contagem: Counter = field(default_factory=Counter)
    encaixes: int = 0

    @property
    def total(self):
        return sum(self.contagem.values())

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
    def cancelados(self):
        return self.contagem[Status.CANCELADO]

    @property
    def liberados(self):
        return self.contagem[Status.EXPIRADO]

    @property
    def ocupacao(self):
        return _porcentagem(self.reservados, self.oferecidos)

    @property
    def taxa_faltas(self):
        return _porcentagem(self.faltas, self.realizados + self.faltas)


def _somar(linha, agendamento):
    linha.contagem[agendamento.status] += 1
    if agendamento.origem != Agendamento.Origem.AUTOAGENDAMENTO:
        linha.encaixes += 1


def resumo(unidade, de: date, ate: date, massoterapeuta=None):
    ags = list(agendamentos(unidade, de, ate, massoterapeuta).select_related("massoterapeuta__usuario"))
    massoterapeutas = (
        [massoterapeuta]
        if massoterapeuta
        else list(
            Massoterapeuta.objects.filter(unidade=unidade)
            .filter(Q(ativo=True) | Q(pk__in={a.massoterapeuta_id for a in ags}))
            .select_related("usuario")
        )
    )
    dias = [de + timedelta(days=n) for n in range((ate - de).days + 1)]

    geral = Linha("Total")
    por_massoterapeuta = {m.pk: Linha(m.nome) for m in massoterapeutas}
    por_semana = {}
    inicio, fim = limites(de, ate)
    for m in massoterapeutas:
        periodos = list(m.disponibilidades.all())
        bloqueios = list(m.bloqueios.filter(inicio__lt=fim, fim__gt=inicio).values_list("inicio", "fim"))
        for dia in dias:
            oferecidos = servicos.horarios_oferecidos(m, dia, periodos, bloqueios)
            por_massoterapeuta[m.pk].oferecidos += oferecidos
            geral.oferecidos += oferecidos
            semana = inicio_da_semana(dia)
            por_semana.setdefault(semana, Linha(f"Semana de {semana:%d/%m}")).oferecidos += oferecidos

    for ag in ags:
        _somar(geral, ag)
        if ag.massoterapeuta_id in por_massoterapeuta:
            _somar(por_massoterapeuta[ag.massoterapeuta_id], ag)
        semana = inicio_da_semana(timezone.localtime(ag.inicio).date())
        _somar(por_semana.setdefault(semana, Linha(f"Semana de {semana:%d/%m}")), ag)

    usuarios_unicos = len({a.colaborador_id for a in ags if a.status == Status.REALIZADO})
    return {
        "geral": geral,
        "usuarios_unicos": usuarios_unicos,
        "por_massoterapeuta": list(por_massoterapeuta.values()),
        "por_semana": [por_semana[s] for s in sorted(por_semana)],
    }
