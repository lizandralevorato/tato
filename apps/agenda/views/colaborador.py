from datetime import date, datetime, timedelta

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import servicos
from ..formatacao import dia as formatar_dia
from ..formatacao import hora as formatar_hora
from ..models import Agendamento, ListaEspera, Massoterapeuta, Unidade
from ..servicos import RegraViolada
from . import acesso


def _unidade_do(usuario):
    if usuario.unidade_id:
        return usuario.unidade
    unidades = list(Unidade.objects.filter(ativa=True)[:2])
    return unidades[0] if len(unidades) == 1 else None


def _sem_unidade(request):
    messages.error(request, "Seu cadastro ainda não tem uma unidade. Fale com o administrador.")
    return render(request, "agenda/colaborador/sem_unidade.html")


@acesso.colaborador
def meus_agendamentos(request):
    servicos.liberar_reservas_sem_checkin()
    unidade = _unidade_do(request.user)
    agora = timezone.now()
    hoje = timezone.localdate()
    proximos = []
    for ag in (
        request.user.agendamentos.filter(status__in=Agendamento.EM_ABERTO, fim__gte=agora)
        .select_related("massoterapeuta__usuario", "massoterapeuta__unidade")
    ):
        checkin_abre, checkin_prazo, checkin_limite = servicos.janela_checkin(ag)
        chegada_abre, chegada_fecha = servicos.janela_chegada(ag)
        politica = servicos.politica_da(ag.massoterapeuta.unidade)
        limite_cancelar = ag.inicio - timedelta(minutes=politica.antecedencia_cancelamento_min)
        aguardando = ag.status == Agendamento.Status.AGENDADO
        proximos.append(
            {
                "ag": ag,
                "descricao": servicos.descrever(ag),
                "aguardando_checkin": aguardando and servicos.checkin_obrigatorio(politica),
                "pode_fazer_checkin": aguardando and checkin_abre <= agora <= checkin_limite,
                "checkin_abre": checkin_abre,
                "checkin_prazo": checkin_prazo,
                "checkin_limite": checkin_limite,
                "pode_cancelar": ag.status in Agendamento.PENDENTES and agora <= limite_cancelar,
                "limite_cancelar": limite_cancelar,
                "pode_avisar_chegada": ag.status in Agendamento.PENDENTES and chegada_abre <= agora <= chegada_fecha,
                "chegada_abre": chegada_abre,
            }
        )
    historico = (
        request.user.agendamentos.exclude(status__in=Agendamento.EM_ABERTO)
        .filter(inicio__gte=agora - timedelta(days=14))
        .select_related("massoterapeuta__usuario")
        .order_by("-inicio")[:5]
    )
    espera = []
    for entrada in request.user.lista_espera.filter(ativa=True, dia__gte=hoje).select_related(
        "massoterapeuta__usuario", "unidade"
    ):
        livres = servicos.horarios_livres(entrada.unidade, entrada.dia, massoterapeuta=entrada.massoterapeuta)
        espera.append({"e": entrada, "livres": len(livres)})
    return render(
        request,
        "agenda/colaborador/meus_agendamentos.html",
        {
            "proximos": proximos,
            "historico": historico,
            "espera": espera,
            "unidade": unidade,
            "restantes": servicos.restantes_na_semana(request.user, unidade, hoje) if unidade else 0,
            "politica": servicos.politica_da(unidade) if unidade else None,
        },
    )


@acesso.colaborador
def agendar_dia(request):
    servicos.liberar_reservas_sem_checkin()
    unidade = _unidade_do(request.user)
    if unidade is None:
        return _sem_unidade(request)
    return render(
        request,
        "agenda/colaborador/agendar_dia.html",
        {
            "dias": servicos.dias_para_agendar(unidade, request.user),
            "restantes": servicos.restantes_na_semana(request.user, unidade),
            "politica": servicos.politica_da(unidade),
        },
    )


@acesso.colaborador
def agendar_horario(request, dia: str):
    servicos.liberar_reservas_sem_checkin()
    unidade = _unidade_do(request.user)
    if unidade is None:
        return _sem_unidade(request)
    try:
        data = date.fromisoformat(dia)
    except ValueError:
        raise Http404
    massoterapeutas = list(unidade.massoterapeutas.filter(ativo=True).select_related("usuario"))
    preferido = next((m for m in massoterapeutas if str(m.pk) == request.GET.get("m")), None)

    agrupados = {}
    for horario in servicos.horarios_livres(unidade, data, massoterapeuta=preferido):
        agrupados.setdefault(horario.inicio, []).append(horario.massoterapeuta)
    opcoes = [
        {
            "inicio": inicio,
            "valor": inicio.isoformat(),
            "rotulo": formatar_hora(inicio),
            "quantos": len(ms),
            "nomes": ", ".join(m.nome for m in ms),
            "periodo": "Manhã" if timezone.localtime(inicio).hour < 12 else "Tarde",
        }
        for inicio, ms in agrupados.items()
    ]
    periodos = {}
    for opcao in opcoes:
        periodos.setdefault(opcao["periodo"], []).append(opcao)

    return render(
        request,
        "agenda/colaborador/agendar_horario.html",
        {
            "data": data,
            "dia_iso": data.isoformat(),
            "periodos": periodos,
            "massoterapeutas": massoterapeutas,
            "preferido": preferido,
            "na_espera": request.user.lista_espera.filter(ativa=True, dia=data).first(),
            "pode_esperar": data >= timezone.localdate(),
        },
    )


def _texto_checkin(agendamento):
    if agendamento.status == Agendamento.Status.CONFIRMADO:
        return "O check-in já está feito."
    abre, prazo, _ = servicos.janela_checkin(agendamento)
    return (
        f"Faça o check-in entre {formatar_hora(abre)} e {formatar_hora(prazo)} do dia da massagem. "
        "Você vai receber um lembrete."
    )


def _ler_escolha(request, dados, unidade):
    try:
        inicio = datetime.fromisoformat(dados.get("inicio", ""))
    except ValueError:
        raise Http404
    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(inicio)
    m_id = dados.get("m")
    if m_id:
        massoterapeuta = get_object_or_404(Massoterapeuta, pk=m_id, unidade=unidade)
    else:
        massoterapeuta = servicos.escolher_massoterapeuta(unidade, inicio)
    return inicio, massoterapeuta


@acesso.colaborador
def agendar_confirmar(request):
    unidade = _unidade_do(request.user)
    if unidade is None:
        return _sem_unidade(request)
    dados = request.POST if request.method == "POST" else request.GET
    if request.method == "GET" and not dados.get("inicio"):
        dia = dados.get("dia", "")
        messages.error(request, "Escolha um horário da lista para continuar.")
        return redirect("agenda:agendar_horario", dia=dia) if dia else redirect("agenda:agendar_dia")

    dia_da_escolha = timezone.localdate()
    try:
        inicio, massoterapeuta = _ler_escolha(request, dados, unidade)
        dia_da_escolha = timezone.localtime(inicio).date()
        if request.method == "POST":
            agendamento = servicos.agendar(request.user, massoterapeuta, inicio)
            messages.success(request, f"Massagem agendada: {servicos.descrever(agendamento)}. {_texto_checkin(agendamento)}")
            return redirect("agenda:meus_agendamentos")
        servicos.validar_agendamento(request.user, massoterapeuta, inicio)
    except RegraViolada as erro:
        messages.error(request, str(erro))
        return redirect("agenda:agendar_horario", dia=dia_da_escolha.isoformat())

    abre, prazo, limite = servicos.janela_checkin(Agendamento(inicio=inicio, massoterapeuta=massoterapeuta))
    return render(
        request,
        "agenda/colaborador/agendar_confirmar.html",
        {
            "checkin_abre": abre,
            "checkin_prazo": prazo,
            "checkin_limite": limite,
            "checkin_ja_aberto": timezone.now() >= abre,
            "inicio": inicio,
            "massoterapeuta": massoterapeuta,
            "descricao_dia": formatar_dia(inicio),
            "hora": formatar_hora(inicio),
            "duracao": massoterapeuta.duracao_sessao_min,
            "politica": servicos.politica_da(unidade),
        },
    )


def _agendamento_do_usuario(request, pk):
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("massoterapeuta__usuario", "massoterapeuta__unidade", "colaborador"),
        pk=pk,
    )
    if agendamento.colaborador_id != request.user.pk and not request.user.eh_equipe:
        raise Http404
    return agendamento


def _destino_apos_acao(request):
    return "agenda:administrador" if request.user.eh_equipe and request.GET.get("de") == "administrador" else "agenda:meus_agendamentos"


@acesso.colaborador
def cancelar(request, pk):
    agendamento = _agendamento_do_usuario(request, pk)
    if request.method == "POST":
        return acesso.executar(
            request,
            servicos.cancelar,
            f"Agendamento cancelado: {servicos.descrever(agendamento, com_colaborador=request.user.eh_equipe)}. O horário ficou livre para outra pessoa.",
            _destino_apos_acao(request),
            agendamento,
            request.user,
        )
    return render(
        request,
        "agenda/colaborador/cancelar.html",
        {
            "agendamento": agendamento,
            "descricao": servicos.descrever(agendamento, com_colaborador=request.user.eh_equipe),
            "de": request.GET.get("de", ""),
        },
    )


@require_POST
@acesso.colaborador
def checkin(request, pk):
    """Check-in: confirma que vai (até 1 h antes, por padrão)."""
    agendamento = _agendamento_do_usuario(request, pk)
    return acesso.executar(
        request,
        servicos.fazer_checkin,
        f"Check-in feito: {servicos.descrever(agendamento)}. Até lá!",
        "agenda:meus_agendamentos",
        agendamento,
    )


@require_POST
@acesso.colaborador
def chegada(request, pk):
    """"Cheguei": avisa o massoterapeuta que a pessoa está na porta da sala."""
    agendamento = _agendamento_do_usuario(request, pk)
    return acesso.executar(
        request,
        servicos.avisar_chegada,
        f"Chegada avisada. {agendamento.massoterapeuta.nome} já sabe que você está aqui.",
        "agenda:meus_agendamentos",
        agendamento,
    )


@require_POST
@acesso.colaborador
def entrar_na_espera(request):
    unidade = _unidade_do(request.user)
    if unidade is None:
        return _sem_unidade(request)
    try:
        dia = date.fromisoformat(request.POST.get("dia", ""))
    except ValueError:
        raise Http404
    massoterapeuta = None
    if request.POST.get("m"):
        massoterapeuta = get_object_or_404(Massoterapeuta, pk=request.POST["m"], unidade=unidade, ativo=True)
    try:
        servicos.entrar_na_lista_de_espera(request.user, unidade, dia, massoterapeuta)
    except RegraViolada as erro:
        messages.error(request, str(erro))
        return redirect("agenda:agendar_horario", dia=dia.isoformat())
    com = f" com {massoterapeuta.nome}" if massoterapeuta else ""
    messages.success(
        request,
        f"Você está na lista de espera de {formatar_dia(dia)}{com}. Se abrir um horário, você recebe um aviso no celular.",
    )
    return redirect("agenda:meus_agendamentos")


@require_POST
@acesso.colaborador
def sair_da_espera(request, pk):
    entrada = get_object_or_404(ListaEspera, pk=pk, colaborador=request.user, ativa=True)
    servicos.sair_da_lista_de_espera(entrada)
    messages.success(request, f"Você saiu da lista de espera de {formatar_dia(entrada.dia)}.")
    return redirect("agenda:meus_agendamentos")
