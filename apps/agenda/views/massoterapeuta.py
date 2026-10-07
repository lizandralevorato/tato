import hashlib
from datetime import timedelta

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import servicos
from ..forms import AusenciaForm, PeriodoForm
from ..formatacao import dia as formatar_dia
from ..formatacao import hora as formatar_hora
from ..models import Agendamento, Massoterapeuta
from ..servicos import ConflitoDeAgenda, RegraViolada
from . import acesso


def _massoterapeuta_de(request):
    try:
        return request.user.massoterapeuta
    except Massoterapeuta.DoesNotExist:
        raise Http404("Cadastro de massoterapeuta não encontrado.")


def _contexto_ao_vivo(massoterapeuta):
    """Dados da parte da tela que se atualiza sozinha (próximo + agenda de hoje)."""
    servicos.liberar_reservas_sem_checkin()
    agora = timezone.now()
    proximo = servicos.proximo_atendimento(massoterapeuta, agora)
    itens = []
    for ag in servicos.agenda_do_dia(massoterapeuta, timezone.localdate()):
        itens.append(
            {
                "ag": ag,
                "pode_atender": ag.status in Agendamento.EM_ABERTO and agora >= ag.inicio,
                "falta_a_partir": servicos.pode_marcar_falta_a_partir(ag),
                "pode_faltar": ag.status in Agendamento.PENDENTES and agora >= servicos.pode_marcar_falta_a_partir(ag),
                "passou": ag.fim < agora,
                "em_aberto": ag.status in Agendamento.EM_ABERTO,
            }
        )
    pendentes = [i for i in itens if i["ag"].status in Agendamento.EM_ABERTO]
    return {
        "proximo": proximo,
        "proximo_falta_a_partir": servicos.pode_marcar_falta_a_partir(proximo) if proximo else None,
        "proximo_pode_faltar": bool(
            proximo
            and proximo.status in Agendamento.PENDENTES
            and agora >= servicos.pode_marcar_falta_a_partir(proximo)
        ),
        "proximo_pode_atender": bool(proximo and agora >= proximo.inicio),
        "itens": itens,
        "total_pendentes": len(pendentes),
        "agora": agora,
    }


def _texto_agenda_falada(massoterapeuta, contexto):
    """Resumo pensado para ser ouvido (botão "Ouvir agenda de hoje")."""
    pendentes = [i["ag"] for i in contexto["itens"] if i["ag"].status in Agendamento.EM_ABERTO]
    if not pendentes:
        return "Você não tem mais atendimentos marcados para hoje."
    frases = [f"Você tem {len(pendentes)} atendimento{'s' if len(pendentes) > 1 else ''} pela frente hoje."]
    for ag in pendentes:
        frases.append(f"{formatar_hora(ag.inicio)}, {ag.colaborador.nome}, {ag.get_status_display().lower()}.")
    return " ".join(frases)


@acesso.massoterapeuta
def agora(request):
    massoterapeuta = _massoterapeuta_de(request)
    contexto = _contexto_ao_vivo(massoterapeuta)
    contexto["massoterapeuta"] = massoterapeuta
    contexto["texto_falado"] = _texto_agenda_falada(massoterapeuta, contexto)
    contexto["estado_inicial"] = _estado(massoterapeuta)
    return render(request, "agenda/massoterapeuta/agora.html", contexto)


@acesso.massoterapeuta
def agora_parcial(request):
    massoterapeuta = _massoterapeuta_de(request)
    contexto = _contexto_ao_vivo(massoterapeuta)
    contexto["texto_falado"] = _texto_agenda_falada(massoterapeuta, contexto)
    return render(request, "agenda/massoterapeuta/_ao_vivo.html", contexto)


def _estado(massoterapeuta):
    itens = [
        {
            "id": ag.pk,
            "hora": formatar_hora(ag.inicio),
            "inicio": ag.inicio.isoformat(),
            "nome": ag.colaborador.nome,
            "status": ag.status,
        }
        for ag in servicos.agenda_do_dia(massoterapeuta, timezone.localdate(), incluir_cancelados=True)
    ]
    assinatura = "|".join(f"{i['id']}:{i['status']}" for i in itens)
    return {"versao": hashlib.sha1(assinatura.encode()).hexdigest()[:12], "itens": itens}


@acesso.massoterapeuta
def estado_json(request):
    servicos.liberar_reservas_sem_checkin()
    return JsonResponse(_estado(_massoterapeuta_de(request)))


def _agendamento_meu(request, pk):
    return get_object_or_404(
        Agendamento.objects.select_related("colaborador", "massoterapeuta__unidade"),
        pk=pk,
        massoterapeuta=_massoterapeuta_de(request),
    )


@require_POST
@acesso.massoterapeuta
def marcar_atendido(request, pk):
    ag = _agendamento_meu(request, pk)
    return acesso.executar(
        request,
        servicos.marcar_realizado,
        f"{formatar_hora(ag.inicio)}, {ag.colaborador.nome}: marcado como atendido.",
        "agenda:agora",
        ag,
        por=request.user,
    )


@require_POST
@acesso.massoterapeuta
def marcar_falta(request, pk):
    ag = _agendamento_meu(request, pk)
    return acesso.executar(
        request,
        servicos.marcar_falta,
        f"{formatar_hora(ag.inicio)}, {ag.colaborador.nome}: marcado como falta. O horário foi registrado.",
        "agenda:agora",
        ag,
        por=request.user,
    )


@require_POST
@acesso.massoterapeuta
def pausar(request):
    massoterapeuta = _massoterapeuta_de(request)
    try:
        minutos = int(request.POST.get("minutos", "0"))
        conflitos = servicos.pausar(massoterapeuta, minutos)
    except (ValueError, RegraViolada) as erro:
        messages.error(request, str(erro) if isinstance(erro, RegraViolada) else "Escolha uma pausa válida.")
        return redirect("agenda:agora")
    texto = f"Pausa de {minutos} minutos registrada. Ninguém novo poderá agendar nesse período."
    if conflitos:
        texto += " Atenção: você já tem atendimento marcado às " + ", ".join(
            formatar_hora(ag.inicio) for ag in conflitos
        ) + "."
        messages.warning(request, texto)
    else:
        messages.success(request, texto)
    return redirect("agenda:agora")


def _descrever_ausencia(bloqueio):
    fim = bloqueio.fim - timedelta(minutes=1)
    if timezone.localtime(bloqueio.inicio).date() == timezone.localtime(fim).date():
        return f"{formatar_dia(bloqueio.inicio)}, das {formatar_hora(bloqueio.inicio)} às {formatar_hora(bloqueio.fim)}"
    return f"de {formatar_dia(bloqueio.inicio)} até {formatar_dia(fim)}"


@acesso.massoterapeuta
def disponibilidade(request):
    massoterapeuta = _massoterapeuta_de(request)
    form_periodo = PeriodoForm(prefix="periodo")
    form_ausencia = AusenciaForm(prefix="ausencia")
    conflitos = []

    if request.method == "POST" and "adicionar_periodo" in request.POST:
        form_periodo = PeriodoForm(request.POST, prefix="periodo")
        if form_periodo.is_valid():
            dados = form_periodo.cleaned_data
            try:
                periodo = servicos.adicionar_periodo(
                    massoterapeuta, dados["dia_semana"], dados["hora_inicio"], dados["hora_fim"]
                )
            except RegraViolada as erro:
                form_periodo.add_error(None, str(erro))
            else:
                messages.success(
                    request,
                    f"Horário adicionado: {periodo.get_dia_semana_display()}, das {formatar_hora(periodo.hora_inicio)} "
                    f"às {formatar_hora(periodo.hora_fim)}. Os novos horários já aparecem para agendar.",
                )
                return redirect("agenda:disponibilidade")

    elif request.method == "POST" and "marcar_ausencia" in request.POST:
        form_ausencia = AusenciaForm(request.POST, prefix="ausencia")
        if form_ausencia.is_valid():
            dados = form_ausencia.cleaned_data
            try:
                bloqueio, cancelados = servicos.marcar_ausencia(
                    massoterapeuta,
                    dados["inicio"],
                    dados["fim"],
                    dados["motivo"],
                    por=request.user,
                    observacao=dados["observacao"],
                    cancelar_agendamentos=dados["cancelar_agendamentos"],
                )
            except ConflitoDeAgenda as erro:
                conflitos = erro.agendamentos
            except RegraViolada as erro:
                form_ausencia.add_error(None, str(erro))
            else:
                texto = f"{bloqueio.get_motivo_display()} registrada: {_descrever_ausencia(bloqueio)}."
                if cancelados:
                    texto += f" {len(cancelados)} agendamento{'s' if len(cancelados) > 1 else ''} cancelado{'s' if len(cancelados) > 1 else ''} e as pessoas foram avisadas."
                messages.success(request, texto)
                return redirect("agenda:disponibilidade")

    bloqueios = [
        {"b": b, "descricao": _descrever_ausencia(b)}
        for b in massoterapeuta.bloqueios.filter(fim__gte=timezone.now()).exclude(motivo="pausa").order_by("inicio")
    ]
    return render(
        request,
        "agenda/massoterapeuta/disponibilidade.html",
        {
            "massoterapeuta": massoterapeuta,
            "periodos": massoterapeuta.disponibilidades.all(),
            "bloqueios": bloqueios,
            "form_periodo": form_periodo,
            "form_ausencia": form_ausencia,
            "conflitos": [servicos.descrever(ag, com_massoterapeuta=False, com_colaborador=True) for ag in conflitos],
        },
    )


@acesso.massoterapeuta
def remover_periodo(request, pk):
    massoterapeuta = _massoterapeuta_de(request)
    periodo = get_object_or_404(massoterapeuta.disponibilidades, pk=pk)
    descricao = (
        f"{periodo.get_dia_semana_display()}, das {formatar_hora(periodo.hora_inicio)} às {formatar_hora(periodo.hora_fim)}"
    )
    afetados = servicos.agendamentos_no_periodo(periodo)
    if request.method == "POST":
        cancelar = bool(request.POST.get("cancelar_agendamentos"))
        servicos.remover_periodo(periodo, por=request.user, cancelar_agendamentos=cancelar)
        texto = f"Horário removido: {descricao}."
        if afetados and cancelar:
            texto += " Os agendamentos desse horário foram cancelados e as pessoas avisadas."
        elif afetados:
            texto += " Os agendamentos já marcados nesse horário continuam valendo."
        messages.success(request, texto)
        return redirect("agenda:disponibilidade")
    return render(
        request,
        "agenda/massoterapeuta/remover_periodo.html",
        {
            "periodo": periodo,
            "descricao": descricao,
            "afetados": [servicos.descrever(ag, com_massoterapeuta=False, com_colaborador=True) for ag in afetados],
        },
    )


@require_POST
@acesso.massoterapeuta
def remover_ausencia(request, pk):
    massoterapeuta = _massoterapeuta_de(request)
    bloqueio = get_object_or_404(massoterapeuta.bloqueios.exclude(motivo="pausa"), pk=pk)
    descricao = _descrever_ausencia(bloqueio)
    servicos.remover_ausencia(bloqueio)
    messages.success(request, f"Ausência removida ({descricao}). Os horários voltaram para a agenda.")
    return redirect("agenda:disponibilidade")
