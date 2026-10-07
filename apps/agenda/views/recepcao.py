from datetime import date, datetime, timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.contas.models import Usuario

from .. import servicos
from ..forms import PessoaForm, PoliticaForm
from ..formatacao import hora as formatar_hora
from ..models import Agendamento, Massoterapeuta, Unidade
from ..servicos import RegraViolada
from . import acesso


def unidade_da_equipe(request):
    if request.user.unidade_id:
        return request.user.unidade
    unidades = Unidade.objects.filter(ativa=True)
    escolhida = request.GET.get("unidade")
    if escolhida and escolhida.isdigit():
        return unidades.filter(pk=escolhida).first() or unidades.first()
    return unidades.first()


def _data(texto, padrao):
    try:
        return date.fromisoformat(texto or "")
    except ValueError:
        return padrao


@acesso.equipe
def agenda_da_unidade(request):
    servicos.liberar_reservas_sem_checkin()
    dia = _data(request.GET.get("dia"), timezone.localdate())
    unidade = unidade_da_equipe(request)
    massoterapeutas = Massoterapeuta.objects.filter(ativo=True, unidade=unidade).select_related("usuario", "unidade")

    colunas = [
        {
            "massoterapeuta": m,
            "agendamentos": servicos.agenda_do_dia(m, dia, incluir_cancelados=True),
            "livres": len(servicos.horarios_do_massoterapeuta(m, dia)),
        }
        for m in massoterapeutas
    ]
    return render(
        request,
        "agenda/recepcao/agenda.html",
        {
            "dia": dia,
            "anterior": dia - timedelta(days=1),
            "seguinte": dia + timedelta(days=1),
            "eh_hoje": dia == timezone.localdate(),
            "colunas": colunas,
        },
    )


def _url_agendar(**params):
    params = {chave: valor for chave, valor in params.items() if valor not in (None, "")}
    return reverse("agenda:recepcao_agendar") + ("?" + urlencode(params) if params else "")


@acesso.equipe
def agendar_para(request):
    """Agendar ou encaixar alguém: 1) escolher a pessoa, 2) massoterapeuta e dia, 3) horário."""
    servicos.liberar_reservas_sem_checkin()
    unidade = unidade_da_equipe(request)
    dados = request.POST if request.method == "POST" else request.GET
    massoterapeutas = list(unidade.massoterapeutas.filter(ativo=True).select_related("usuario")) if unidade else []

    colaborador = None
    if dados.get("colaborador"):
        colaborador = get_object_or_404(
            Usuario.objects.exclude(papel=Usuario.Papel.MASSOTERAPEUTA), pk=dados["colaborador"], is_active=True
        )
    escolhido = next((m for m in massoterapeutas if str(m.pk) == dados.get("m")), None)
    dia = _data(dados.get("dia"), None)

    if request.method == "POST" and colaborador:
        try:
            agendamento = _agendar_pela_equipe(request, colaborador, escolhido, massoterapeutas)
        except RegraViolada as erro:
            messages.error(request, str(erro))
            return redirect(_url_agendar(colaborador=colaborador.pk, m=dados.get("m"), dia=dados.get("dia")))
        messages.success(
            request,
            f"Agendado para {colaborador.nome}: {servicos.descrever(agendamento)}. A pessoa recebe um aviso no celular.",
        )
        return redirect(reverse("agenda:recepcao") + f"?dia={timezone.localtime(agendamento.inicio).date().isoformat()}")

    busca = dados.get("q", "").strip()
    resultados = []
    if busca and not colaborador:
        resultados = (
            Usuario.objects.filter(is_active=True)
            .exclude(papel=Usuario.Papel.MASSOTERAPEUTA)
            .filter(Q(first_name__icontains=busca) | Q(last_name__icontains=busca) | Q(email__icontains=busca))
            .order_by("first_name", "last_name")[:20]
        )

    horarios = []
    uso = None
    if colaborador and dia:
        horarios = [
            {"valor": f"{h.massoterapeuta.pk}|{h.inicio.isoformat()}", "rotulo": formatar_hora(h.inicio), "m": h.massoterapeuta}
            for h in servicos.horarios_livres(unidade, dia, massoterapeuta=escolhido)
        ]
        politica = servicos.politica_da(unidade)
        uso = {"usadas": servicos.uso_na_semana(colaborador, dia, politica), "maximo": politica.max_por_semana}

    return render(
        request,
        "agenda/recepcao/agendar.html",
        {
            "busca": busca,
            "resultados": resultados,
            "colaborador": colaborador,
            "massoterapeutas": massoterapeutas,
            "escolhido": escolhido,
            "dia": dia,
            "hoje": timezone.localdate(),
            "horarios": horarios,
            "uso": uso,
        },
    )


def _agendar_pela_equipe(request, colaborador, escolhido, massoterapeutas):
    dados = request.POST
    excecao = bool(dados.get("excecao"))
    opcao = dados.get("horario", "")
    if opcao == "encaixe":
        massoterapeuta = escolhido or next((m for m in massoterapeutas if str(m.pk) == dados.get("m_encaixe")), None)
        if massoterapeuta is None:
            raise RegraViolada("Para o encaixe, escolha o massoterapeuta.")
        try:
            dia = date.fromisoformat(dados.get("dia", ""))
            hora = datetime.strptime(dados.get("hora_encaixe", ""), "%H:%M").time()
        except ValueError:
            raise RegraViolada("Informe a hora do encaixe, por exemplo 10h15.")
        inicio = timezone.make_aware(datetime.combine(dia, hora))
        return servicos.agendar(colaborador, massoterapeuta, inicio, por=request.user, encaixe=True, excecao=excecao)

    try:
        m_id, inicio_iso = opcao.split("|", 1)
        massoterapeuta = next(m for m in massoterapeutas if str(m.pk) == m_id)
        inicio = datetime.fromisoformat(inicio_iso)
    except (ValueError, StopIteration):
        raise RegraViolada("Escolha um horário da lista ou o encaixe.")
    return servicos.agendar(colaborador, massoterapeuta, inicio, por=request.user, excecao=excecao)


def _agendamento_da_unidade(request, pk):
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade"), pk=pk
    )
    if request.user.unidade_id and agendamento.massoterapeuta.unidade_id != request.user.unidade_id:
        raise Http404
    return agendamento


@acesso.equipe
def agendamento_detalhe(request, pk):
    agendamento = _agendamento_da_unidade(request, pk)
    agora = timezone.now()
    return render(
        request,
        "agenda/recepcao/agendamento.html",
        {
            "ag": agendamento,
            "descricao": servicos.descrever(agendamento, com_colaborador=True),
            "historico": agendamento.historico.select_related("por"),
            "pode_cancelar": agendamento.status in Agendamento.PENDENTES,
            "pode_atender": agendamento.status in Agendamento.EM_ABERTO and agora >= agendamento.inicio,
            "pode_faltar": agendamento.status in Agendamento.PENDENTES
            and agora >= servicos.pode_marcar_falta_a_partir(agendamento),
        },
    )


@require_POST
@acesso.equipe
def marcar_pela_equipe(request, pk, acao):
    agendamento = _agendamento_da_unidade(request, pk)
    funcoes = {
        "atendido": (servicos.marcar_realizado, "marcado como atendido"),
        "faltou": (servicos.marcar_falta, "marcado como falta"),
    }
    if acao not in funcoes:
        raise Http404
    funcao, texto = funcoes[acao]
    return acesso.executar(
        request,
        funcao,
        f"{formatar_hora(agendamento.inicio)}, {agendamento.colaborador.nome}: {texto}.",
        reverse("agenda:recepcao_agendamento", args=[agendamento.pk]),
        agendamento,
        por=request.user,
    )


# Cadastros


@acesso.equipe
def pessoas(request):
    unidade = unidade_da_equipe(request)
    busca = request.GET.get("q", "").strip()
    papel = request.GET.get("papel", "")
    qs = Usuario.objects.select_related("unidade").order_by("first_name", "last_name")
    if request.user.unidade_id:
        qs = qs.filter(Q(unidade_id=request.user.unidade_id) | Q(unidade__isnull=True))
    if busca:
        qs = qs.filter(Q(first_name__icontains=busca) | Q(last_name__icontains=busca) | Q(email__icontains=busca))
    if papel in Usuario.Papel.values:
        qs = qs.filter(papel=papel)
    return render(
        request,
        "agenda/recepcao/pessoas.html",
        {
            "pessoas": qs[:200],
            "total": qs.count(),
            "busca": busca,
            "papel": papel,
            "papeis": Usuario.Papel.choices,
            "unidade": unidade,
        },
    )


@transaction.atomic
def _salvar_pessoa(form, usuario):
    dados = form.cleaned_data
    massoterapeuta = getattr(usuario, "massoterapeuta", None) if usuario.pk else None
    if massoterapeuta and dados["papel"] != Usuario.Papel.MASSOTERAPEUTA:
        massoterapeuta.delete()
        massoterapeuta = None
    for campo in ("first_name", "last_name", "email", "papel", "unidade", "is_active"):
        setattr(usuario, campo, dados[campo])
    if dados.get("nova_senha"):
        usuario.set_password(dados["nova_senha"])
    usuario.save()
    if dados["papel"] == Usuario.Papel.MASSOTERAPEUTA:
        massoterapeuta = massoterapeuta or Massoterapeuta(usuario=usuario)
        massoterapeuta.unidade = dados["unidade"]
        massoterapeuta.duracao_sessao_min = dados["duracao_sessao_min"]
        massoterapeuta.intervalo_min = dados["intervalo_min"]
        massoterapeuta.ativo = dados["atendendo"]
        massoterapeuta.save()
    return usuario


@acesso.equipe
def pessoa(request, pk=None):
    usuario = get_object_or_404(Usuario, pk=pk) if pk else None
    if usuario and request.user.unidade_id and usuario.unidade_id not in (None, request.user.unidade_id):
        raise Http404
    if usuario and usuario.is_superuser and not request.user.is_superuser:
        raise Http404
    form = PessoaForm(request.POST or None, instance=usuario)
    if not usuario and request.method == "GET":
        form.initial["unidade"] = unidade_da_equipe(request)
        form.initial["papel"] = Usuario.Papel.COLABORADOR
    if request.method == "POST" and form.is_valid():
        criado = usuario is None
        usuario = _salvar_pessoa(form, usuario or Usuario())
        if criado:
            messages.success(request, f"{usuario.nome} cadastrado(a). Passe o e-mail e a senha para a pessoa.")
        else:
            messages.success(request, f"Cadastro de {usuario.nome} atualizado.")
        return redirect("agenda:pessoas")
    return render(request, "agenda/recepcao/pessoa.html", {"form": form, "pessoa": usuario})


@acesso.equipe
def regras(request):
    unidade = unidade_da_equipe(request)
    if unidade is None:
        raise Http404("Nenhuma unidade cadastrada.")
    politica = servicos.politica_da(unidade)
    form = PoliticaForm(request.POST or None, instance=politica)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Regras do benefício salvas. Elas já valem para os próximos agendamentos.")
        return redirect("agenda:regras")
    return render(request, "agenda/recepcao/regras.html", {"form": form, "unidade": unidade})
