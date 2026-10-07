"""Envio de Web Push (gratuito, padrão dos navegadores, chaves VAPID próprias).

Nada aqui pode derrubar uma tela: falhas ficam registradas na Notificacao e o
comando `notificacoes` tenta de novo.
"""

import json
import logging

import requests
from django.conf import settings
from django.utils import timezone
from pywebpush import WebPushException, webpush

from apps.contas.models import PerfilAcessibilidade

log = logging.getLogger(__name__)

MAX_TENTATIVAS = 5

# Padrões de vibração iguais aos do anunciador.js (Android).
VIBRACAO = {
    "chegada": [150, 100, 150],
    "cancelamento": [600],
    "liberado": [600],
    "proximo": [300, 100, 300, 100, 300],
    "ultimo_aviso": [300, 100, 300, 100, 300],
    "vaga": [300, 100, 300],
}
VIBRACAO_PADRAO = [150]


def configurado():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def montar_payload(notificacao):
    perfil, _ = PerfilAcessibilidade.objects.get_or_create(usuario=notificacao.usuario)
    dados = {
        "id": notificacao.pk,
        "tipo": notificacao.tipo,
        "titulo": notificacao.titulo,
        "corpo": notificacao.corpo,
        "url": notificacao.url,
        "urgente": notificacao.urgente,
        "tag": f"ag-{notificacao.agendamento_id}" if notificacao.agendamento_id else f"n-{notificacao.pk}",
        "vibrar": VIBRACAO.get(notificacao.tipo, VIBRACAO_PADRAO) if perfil.vibracao else [],
        "silencioso": not perfil.som,
    }
    if notificacao.tipo in (notificacao.Tipo.LEMBRETE, notificacao.Tipo.ULTIMO_AVISO):
        dados["acoes"] = [
            {"id": "vou", "titulo": "Fazer check-in", "url": notificacao.url},
            {"id": "nao-vou", "titulo": "Não vou", "url": notificacao.url},
        ]
    return json.dumps(dados, ensure_ascii=False)


def enviar(notificacao):
    """Envia para todos os aparelhos da pessoa. Devolve True se ao menos um recebeu."""
    try:
        return _enviar(notificacao)
    except Exception:  # noqa: BLE001 (um erro de envio não pode quebrar a tela de quem gerou o aviso)
        log.exception("Falha inesperada ao enviar notificação %s", notificacao.pk)
        return False


def _enviar(notificacao):
    agora = timezone.now()
    if not configurado():
        notificacao.erro = "Web Push não configurado (faltam as chaves VAPID)."
        notificacao.save(update_fields=["erro"])
        return False

    inscricoes = list(notificacao.usuario.inscricoes_push.all())
    if not inscricoes:
        notificacao.erro = "A pessoa não ativou notificações em nenhum aparelho."
        notificacao.tentativas = MAX_TENTATIVAS  # não adianta tentar de novo
        notificacao.save(update_fields=["erro", "tentativas"])
        return False

    payload = montar_payload(notificacao)
    validade = max(int(notificacao.validade_seg), 60)
    erros = []
    recebida = False
    for inscricao in inscricoes:
        try:
            webpush(
                subscription_info=inscricao.como_dict,
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_CONTATO},
                ttl=validade,
                timeout=5,
                headers={"Urgency": "high" if notificacao.urgente else "normal"},
            )
        except WebPushException as erro:
            status = getattr(erro.response, "status_code", None)
            if status in (404, 410):
                inscricao.delete()  # aparelho desinstalou ou revogou a permissão
            else:
                erros.append(f"{status or ''} {erro}".strip())
        except requests.RequestException as erro:
            erros.append(str(erro))
        else:
            recebida = True
            inscricao.ultimo_envio_em = agora
            inscricao.save(update_fields=["ultimo_envio_em"])

    notificacao.tentativas += 1
    if recebida:
        notificacao.enviada_em = agora
        notificacao.erro = ""
    else:
        notificacao.erro = ("; ".join(erros) or "Nenhum aparelho ativo.")[:300]
        if not erros:
            notificacao.tentativas = MAX_TENTATIVAS
    notificacao.save(update_fields=["tentativas", "enviada_em", "erro"])
    return recebida
