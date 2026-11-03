from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from apps.agenda.formatacao import hora as formatar_hora
from apps.agenda.models import Agendamento, Massoterapeuta
from apps.contas.models import PerfilAcessibilidade

from .. import servicos
from ..models import AcessoFicha, FichaSaude
from ..permissoes import massoterapeuta as so_massoterapeuta


@never_cache
@require_safe
@so_massoterapeuta
def ficha_do_atendimento(request, pk):
    """Ficha de uma pessoa só, aberta pelo massoterapeuta do atendimento, dentro da janela de acesso.

    Atendimento de outro massoterapeuta: 404 (nem revela que existe). Meu, mas fora da janela ou
    cancelado: 403. Cada abertura fica registrada.
    """
    try:
        meu = request.user.massoterapeuta
    except Massoterapeuta.DoesNotExist:
        raise Http404
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade"),
        pk=pk,
        massoterapeuta=meu,
    )
    agora = timezone.now()
    if not servicos.pode_abrir_ficha(request.user, agendamento, agora):
        raise PermissionDenied
    ficha = FichaSaude.objects.filter(usuario=agendamento.colaborador).first()
    if ficha is None:
        raise Http404
    servicos.registrar_acesso(
        request.user, agendamento.colaborador, AcessoFicha.Finalidade.ATENDIMENTO, agendamento, agora
    )
    recorrentes = servicos.recorrencias(agendamento.colaborador, agora)
    perfil, _ = PerfilAcessibilidade.objects.get_or_create(usuario=request.user)
    nome = agendamento.colaborador.nome
    hora = formatar_hora(agendamento.inicio)
    return render(
        request,
        "ficha/ficha_do_atendimento.html",
        {
            "agendamento": agendamento,
            "ficha": ficha,
            "titulo_pagina": f"Ficha de {nome}, atendimento às {hora}",
            "secoes": servicos.secoes_da_ficha(agendamento, ficha, recorrentes),
            "voltar": reverse("agenda:agora") + f"#atendimento-{agendamento.pk}",
            "mostrar_aviso_fala": not perfil.ocultar_aviso_fala_ficha,
            "foco_no_titulo": True,
        },
    )


@require_POST
@so_massoterapeuta
def ocultar_aviso_fala(request):
    """"Não mostrar de novo" o aviso de fones antes de ouvir a ficha."""
    PerfilAcessibilidade.objects.update_or_create(usuario=request.user, defaults={"ocultar_aviso_fala_ficha": True})
    return HttpResponse(status=204)
