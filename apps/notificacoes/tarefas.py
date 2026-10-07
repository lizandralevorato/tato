"""Trabalho periódico: roda a cada minuto pelo comando `manage.py notificacoes`.

Cada função é idempotente (o banco impede o mesmo aviso duas vezes), então
rodar a mais ou dois processos ao mesmo tempo não duplica notificações.
"""

from datetime import timedelta

from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import Agendamento, PoliticaBeneficio

from . import avisos, push
from .models import Notificacao

Status = Agendamento.Status


def enviar_lembretes(agora=None):
    """Lembrete de check-in: sai quando o check-in abre, para quem ainda não fez."""
    agora = agora or timezone.now()
    enviados = 0
    for politica in PoliticaBeneficio.objects.all():
        if not servicos.checkin_obrigatorio(politica):
            continue
        abre_min = max(politica.checkin_abre_min, politica.checkin_prazo_min)
        pendentes = (
            Agendamento.objects.filter(
                massoterapeuta__unidade_id=politica.unidade_id,
                status=Status.AGENDADO,
                inicio__gt=agora + timedelta(minutes=politica.checkin_prazo_min),
                inicio__lte=agora + timedelta(minutes=abre_min),
            )
            .exclude(notificacoes__tipo=Notificacao.Tipo.LEMBRETE)
            .select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade")
        )
        for agendamento in pendentes:
            _, prazo, limite = servicos.janela_checkin(agendamento)
            if avisos.lembrete(agendamento, prazo, limite):
                enviados += 1
    return enviados


def avisar_prazo_checkin(agora=None):
    """Último aviso: o prazo do check-in chegou e só resta a tolerância."""
    agora = agora or timezone.now()
    enviados = 0
    for politica in PoliticaBeneficio.objects.all():
        if not servicos.checkin_obrigatorio(politica) or not politica.checkin_tolerancia_min:
            continue
        no_prazo = (
            Agendamento.objects.filter(
                massoterapeuta__unidade_id=politica.unidade_id,
                status=Status.AGENDADO,
                inicio__gt=agora + timedelta(minutes=politica.checkin_prazo_min - politica.checkin_tolerancia_min),
                inicio__lte=agora + timedelta(minutes=politica.checkin_prazo_min),
            )
            .exclude(notificacoes__tipo=Notificacao.Tipo.ULTIMO_AVISO)
            .select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade")
        )
        for agendamento in no_prazo:
            _, _, limite = servicos.janela_checkin(agendamento)
            if avisos.ultimo_aviso_checkin(agendamento, limite):
                enviados += 1
    return enviados


def avisar_proximos(agora=None):
    """Avisa o massoterapeuta alguns minutos antes de cada atendimento."""
    agora = agora or timezone.now()
    enviados = 0
    for politica in PoliticaBeneficio.objects.select_related("unidade"):
        if not politica.aviso_proximo_min:
            continue
        proximos = (
            Agendamento.objects.filter(
                massoterapeuta__unidade=politica.unidade,
                status__in=Agendamento.EM_ABERTO,
                inicio__gt=agora,
                inicio__lte=agora + timedelta(minutes=politica.aviso_proximo_min),
            )
            .exclude(notificacoes__tipo=Notificacao.Tipo.PROXIMO)
            .select_related("colaborador", "massoterapeuta__usuario")
        )
        for agendamento in proximos:
            minutos = max(int((agendamento.inicio - agora).total_seconds() // 60), 1)
            if avisos.proximo_atendimento(agendamento, minutos):
                enviados += 1
    return enviados


def reenviar_falhas(agora=None):
    """Tenta de novo avisos recentes que não chegaram (sem internet, serviço fora)."""
    agora = agora or timezone.now()
    reenviadas = 0
    for notificacao in Notificacao.objects.filter(
        enviada_em__isnull=True,
        tentativas__gt=0,
        tentativas__lt=push.MAX_TENTATIVAS,
        criada_em__gte=agora - timedelta(minutes=30),
    ).select_related("usuario"):
        if push.enviar(notificacao):
            reenviadas += 1
    return reenviadas


def rodar_ciclo(agora=None):
    agora = agora or timezone.now()
    # Liberar primeiro: quem perdeu o prazo não deve receber "último aviso" depois.
    return {
        "liberadas": len(servicos.liberar_reservas_sem_checkin(agora)),
        "lembretes": enviar_lembretes(agora),
        "ultimos_avisos": avisar_prazo_checkin(agora),
        "proximos": avisar_proximos(agora),
        "reenviadas": reenviar_falhas(agora),
    }
