"""Quem é avisado de quê. Chamado pelas regras da agenda e pelo comando periódico.

O envio acontece depois que a transação do banco confirma (on_commit), para
nunca avisar de algo que acabou não sendo gravado.
"""

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.agenda.formatacao import dia, hora

from . import push, tokens
from .models import Notificacao

Tipo = Notificacao.Tipo


def notificar(usuario, tipo, titulo, corpo, url="/", agendamento=None, urgente=False, validade_seg=3600):
    if agendamento is not None:
        try:
            with transaction.atomic():
                notificacao, criada = Notificacao.objects.get_or_create(
                    usuario=usuario,
                    agendamento=agendamento,
                    tipo=tipo,
                    defaults={"titulo": titulo, "corpo": corpo, "url": url, "urgente": urgente, "validade_seg": validade_seg},
                )
        except IntegrityError:  # outro processo criou o mesmo aviso ao mesmo tempo
            return None
        if not criada:
            return notificacao
    else:
        notificacao = Notificacao.objects.create(
            usuario=usuario, tipo=tipo, titulo=titulo, corpo=corpo, url=url, urgente=urgente, validade_seg=validade_seg
        )
    transaction.on_commit(lambda: push.enviar(notificacao))
    return notificacao


def _eh_hoje(agendamento):
    return timezone.localtime(agendamento.inicio).date() == timezone.localdate()


def _segundos_ate(momento):
    return max(int((momento - timezone.now()).total_seconds()), 60)


def _url_agenda():
    return reverse("agenda:agora")


def _quando_massagem(agendamento):
    texto_dia = dia(agendamento.inicio)
    return f"{texto_dia[0].upper()}{texto_dia[1:]}, às {hora(agendamento.inicio)}, com {agendamento.massoterapeuta.nome}"


def ao_agendar(agendamento, por=None):
    """Avisa o massoterapeuta se for hoje e a pessoa se quem agendou foi a recepção."""
    avisos = []
    if _eh_hoje(agendamento):
        avisos.append(
            notificar(
                agendamento.massoterapeuta.usuario,
                Tipo.NOVO_AGENDAMENTO,
                "Novo agendamento",
                f"Hoje, {hora(agendamento.inicio)}: {agendamento.colaborador.nome}.",
                url=_url_agenda(),
                agendamento=agendamento,
                validade_seg=_segundos_ate(agendamento.inicio),
            )
        )
    if por is not None:
        avisos.append(
            notificar(
                agendamento.colaborador,
                Tipo.NOVO_AGENDAMENTO,
                "Massagem agendada para você",
                f"A recepção agendou sua massagem: {_quando_massagem(agendamento)}.",
                url=reverse("agenda:meus_agendamentos"),
                agendamento=agendamento,
                validade_seg=_segundos_ate(agendamento.inicio),
            )
        )
    return avisos


def ao_chegar(agendamento):
    return notificar(
        agendamento.massoterapeuta.usuario,
        Tipo.CHEGADA,
        f"{agendamento.colaborador.nome} chegou",
        f"{agendamento.colaborador.nome} chegou. Atendimento das {hora(agendamento.inicio)}.",
        url=_url_agenda(),
        agendamento=agendamento,
        urgente=True,
        validade_seg=15 * 60,
    )


def ao_cancelar(agendamento, por):
    massoterapeuta = agendamento.massoterapeuta
    avisos = []
    if _eh_hoje(agendamento) and (por is None or por.pk != massoterapeuta.usuario_id):
        avisos.append(
            notificar(
                massoterapeuta.usuario,
                Tipo.CANCELAMENTO,
                "Agendamento cancelado",
                f"Cancelado: {hora(agendamento.inicio)}, {agendamento.colaborador.nome}. O horário ficou livre.",
                url=_url_agenda(),
                agendamento=agendamento,
                urgente=True,
                validade_seg=_segundos_ate(agendamento.inicio),
            )
        )
    if por is not None and por.pk != agendamento.colaborador_id:
        if por.pk == massoterapeuta.usuario_id:
            corpo = (
                f"{massoterapeuta.nome} não vai poder atender na sua massagem de {dia(agendamento.inicio)}, "
                f"às {hora(agendamento.inicio)}. Se quiser, agende outro horário."
            )
        else:
            corpo = (
                f"A recepção cancelou sua massagem de {dia(agendamento.inicio)}, às {hora(agendamento.inicio)}. "
                "Se quiser, agende outro horário."
            )
        avisos.append(
            notificar(
                agendamento.colaborador,
                Tipo.CANCELAMENTO,
                "Sua massagem foi cancelada",
                corpo,
                url=reverse("agenda:agendar_dia"),
                agendamento=agendamento,
                urgente=True,
                validade_seg=_segundos_ate(agendamento.inicio),
            )
        )
    return avisos


def proximo_atendimento(agendamento, minutos):
    return notificar(
        agendamento.massoterapeuta.usuario,
        Tipo.PROXIMO,
        f"Próximo em {minutos} minutos",
        f"Próximo atendimento em {minutos} minutos: {hora(agendamento.inicio)}, {agendamento.colaborador.nome}.",
        url=_url_agenda(),
        agendamento=agendamento,
        validade_seg=minutos * 60,
    )


def _url_lembrete(agendamento):
    return reverse("notificacoes:lembrete", args=[tokens.gerar(agendamento)])


def lembrete(agendamento, prazo, limite, abre=None):
    """Lembrete da massagem, com botões Fazer check-in / Não vou.

    `abre` só é informado quando o check-in ainda não abriu.
    """
    quando_checkin = (
        f"O check-in abre às {hora(abre)} e vai até {hora(prazo)}."
        if abre
        else f"Faça o check-in até {hora(prazo)}."
    )
    return notificar(
        agendamento.colaborador,
        Tipo.LEMBRETE,
        "Lembrete da sua massagem" if abre else "Faça o check-in da massagem",
        f"{_quando_massagem(agendamento)}. {quando_checkin} "
        f"Sem check-in até {hora(limite)}, a reserva é liberada para outra pessoa.",
        url=_url_lembrete(agendamento),
        agendamento=agendamento,
        validade_seg=_segundos_ate(limite),
    )


def ultimo_aviso_checkin(agendamento, limite):
    return notificar(
        agendamento.colaborador,
        Tipo.ULTIMO_AVISO,
        "Último aviso: faça o check-in",
        f"Faça o check-in até {hora(limite)} ou sua massagem das {hora(agendamento.inicio)} "
        "será liberada para outra pessoa.",
        url=_url_lembrete(agendamento),
        agendamento=agendamento,
        urgente=True,
        validade_seg=_segundos_ate(limite),
    )


def ao_liberar(agendamento):
    """Reserva liberada por falta de check-in: avisa a pessoa e, se for hoje, o massoterapeuta."""
    avisos = [
        notificar(
            agendamento.colaborador,
            Tipo.LIBERADO,
            "Reserva liberada",
            f"Sua massagem de {dia(agendamento.inicio)}, às {hora(agendamento.inicio)}, foi liberada "
            "porque o check-in não foi feito a tempo. Se ainda quiser, veja se há outro horário.",
            url=reverse("agenda:agendar_dia"),
            agendamento=agendamento,
            validade_seg=_segundos_ate(agendamento.inicio),
        )
    ]
    if _eh_hoje(agendamento):
        avisos.append(
            notificar(
                agendamento.massoterapeuta.usuario,
                Tipo.LIBERADO,
                "Horário liberado",
                f"Liberado: {hora(agendamento.inicio)}, {agendamento.colaborador.nome} não fez check-in. "
                "O horário está livre.",
                url=_url_agenda(),
                agendamento=agendamento,
                validade_seg=_segundos_ate(agendamento.inicio),
            )
        )
    return avisos


def vaga_aberta(entrada, agendamento_liberado):
    url = reverse("agenda:agendar_horario", args=[entrada.dia.isoformat()])
    if entrada.massoterapeuta_id:
        url += f"?m={entrada.massoterapeuta_id}"
    return notificar(
        entrada.colaborador,
        Tipo.VAGA,
        "Abriu uma vaga",
        f"Abriu um horário {dia(agendamento_liberado.inicio)}, às {hora(agendamento_liberado.inicio)}, "
        f"com {agendamento_liberado.massoterapeuta.nome}. Quem agendar primeiro fica com ele.",
        url=url,
        agendamento=agendamento_liberado,
        urgente=True,
        validade_seg=_segundos_ate(agendamento_liberado.inicio),
    )


def comunicado(comunicado, usuarios):
    resumo = comunicado.texto if len(comunicado.texto) <= 200 else comunicado.texto[:197].rstrip() + "..."
    return [
        notificar(
            usuario,
            Tipo.COMUNICADO,
            f"Comunicado: {comunicado.titulo}"[:120],
            resumo,
            url=reverse("comunicados:lista"),
            validade_seg=60 * 60 * 24,
        )
        for usuario in usuarios
    ]
