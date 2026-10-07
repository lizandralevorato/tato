import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.agenda import servicos
from apps.agenda.models import Agendamento
from apps.agenda.servicos import RegraViolada

from . import push, tokens
from .models import InscricaoPush, Notificacao

# Troque ao mudar sw.js ou os arquivos guardados para uso sem internet.
VERSAO_SW = "2026-09-30.2"


@never_cache
def service_worker(request):
    resposta = render(request, "notificacoes/sw.js", {"versao": VERSAO_SW}, content_type="application/javascript")
    resposta["Service-Worker-Allowed"] = "/"
    return resposta


def offline(request):
    return render(request, "notificacoes/offline.html")


def _json(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None


@require_POST
@login_required
def inscrever(request):
    dados = _json(request)
    chaves = (dados or {}).get("keys") or {}
    endpoint = (dados or {}).get("endpoint", "")
    if not endpoint.startswith("https://") or not chaves.get("p256dh") or not chaves.get("auth"):
        return HttpResponseBadRequest("Inscrição inválida.")
    InscricaoPush.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "usuario": request.user,
            "p256dh": chaves["p256dh"],
            "auth": chaves["auth"],
            "aparelho": request.headers.get("User-Agent", "")[:200],
        },
    )
    return JsonResponse({"ok": True}, status=201)


@require_POST
@login_required
def remover_inscricao(request):
    endpoint = (_json(request) or {}).get("endpoint", "")
    removidas, _ = InscricaoPush.objects.filter(usuario=request.user, endpoint=endpoint).delete()
    return JsonResponse({"ok": True, "removidas": removidas})


@require_POST
@login_required
def teste(request):
    # Envio síncrono: a pessoa está esperando a resposta na tela.
    notificacao = Notificacao.objects.create(
        usuario=request.user,
        tipo=Notificacao.Tipo.TESTE,
        titulo="Notificação de teste",
        corpo="As notificações estão funcionando neste aparelho.",
        validade_seg=300,
    )
    enviada = push.enviar(notificacao)
    return JsonResponse({"ok": enviada, "erro": notificacao.erro}, status=200 if enviada else 502)


def _responder(request, ok, mensagem, agendamento=None, status=200):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse({"ok": ok, "mensagem": mensagem}, status=status)
    return render(
        request,
        "notificacoes/lembrete_resultado.html",
        {"ok": ok, "mensagem": mensagem, "agendamento": agendamento},
        status=status,
    )


@csrf_exempt  # o próprio link assinado autoriza a ação (vem da notificação, sem sessão)
@never_cache
def lembrete(request, token):
    agendamento_id = tokens.ler(token)
    agendamento = (
        Agendamento.objects.select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade")
        .filter(pk=agendamento_id)
        .first()
        if agendamento_id
        else None
    )
    if agendamento is None:
        return _responder(request, False, "Este lembrete expirou. Abra Meus agendamentos para ver seus horários.", status=410)

    # Garante o estado atual mesmo se o processador periódico estiver atrasado.
    servicos.liberar_reservas_sem_checkin()
    agendamento.refresh_from_db()

    descricao = servicos.descrever(agendamento)
    if request.method != "POST":
        abre, prazo, limite = servicos.janela_checkin(agendamento)
        agora = timezone.now()
        return render(
            request,
            "notificacoes/lembrete.html",
            {
                "agendamento": agendamento,
                "descricao": descricao,
                "pendente": agendamento.status == Agendamento.Status.AGENDADO,
                "checkin_aberto": abre <= agora <= limite,
                "abre": abre,
                "prazo": prazo,
                "limite": limite,
            },
        )

    acao = request.POST.get("acao")
    try:
        if acao == "vou":
            if agendamento.status != Agendamento.Status.CONFIRMADO:
                servicos.fazer_checkin(agendamento)
            return _responder(request, True, f"Check-in feito: {descricao}. Até lá!", agendamento)
        if acao == "nao-vou":
            servicos.cancelar(agendamento, por=agendamento.colaborador)
            return _responder(
                request, True, f"Massagem cancelada: {descricao}. Obrigado por liberar o horário.", agendamento
            )
    except RegraViolada as erro:
        return _responder(request, False, str(erro), agendamento, status=409)
    return _responder(request, False, "Escolha Fazer check-in ou Não vou.", agendamento, status=400)
