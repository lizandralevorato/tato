"""Painel de saúde do SESMT: fichas, regiões, condições e acessos.

Só o papel SESMT entra aqui (nem o administrador, nem o superusuário). Toda abertura de ficha
individual e toda planilha baixada ficam no registro de acessos.
"""

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.agenda.models import Unidade
from apps.contas.models import Usuario
from apps.ficha import indicadores, servicos
from apps.ficha.models import AcessoFicha, FichaSaude
from apps.ficha.permissoes import sesmt
from apps.ficha.vocabulario import nome_curto_regiao

from apps.painel.indicadores import limites

from . import exportacao
from .views import _consulta, _csv, _filtros, _xlsx


def _contexto_filtros(request, filtros):
    return {
        **filtros,
        "unidades": Unidade.objects.filter(ativa=True) if not request.user.unidade_id else [],
        "sem_massoterapeuta": True,
        "consulta": _consulta(filtros),
    }


def _texto_do_ranking(ranking):
    """Alternativa em texto para o ranking: as regiões mais citadas nas fichas."""
    citadas = [f"{nome_curto_regiao(linha['regiao'])} ({linha['fichas']})" for linha in ranking if linha["fichas"]][:3]
    if not citadas:
        return "Ainda não há regiões informadas nas fichas."
    return "Regiões mais citadas nas fichas, com o número de pessoas: " + ", ".join(citadas) + "."


@never_cache
@sesmt
def saude(request):
    filtros = _filtros(request)
    unidade = filtros["unidade"]
    dados = indicadores.resumo(unidade, filtros["de"], filtros["ate"]) if unidade else None
    return render(
        request,
        "painel/saude.html",
        {
            **_contexto_filtros(request, filtros),
            "dados": dados,
            "texto_ranking": _texto_do_ranking(dados["ranking"]) if dados else "",
        },
    )


def _pessoa_da_unidade(request, pk):
    pessoa = get_object_or_404(Usuario.objects.exclude(papel=Usuario.Papel.MASSOTERAPEUTA), pk=pk)
    if request.user.unidade_id and pessoa.unidade_id != request.user.unidade_id:
        raise Http404
    return pessoa


@never_cache
@sesmt
def fichas(request):
    """Quem tem ficha na unidade, com busca por nome."""
    filtros = _filtros(request)
    unidade = filtros["unidade"]
    busca = request.GET.get("q", "").strip()
    linhas = []
    sem_autorizacao = 0
    if unidade:
        todas = FichaSaude.objects.filter(usuario__in=indicadores.colaboradores_da_unidade(unidade))
        sem_autorizacao = todas.filter(autoriza_sesmt=False).count()
        qs = todas.filter(autoriza_sesmt=True).select_related("usuario")
        if busca:
            qs = qs.filter(
                Q(usuario__first_name__icontains=busca) | Q(usuario__last_name__icontains=busca) | Q(usuario__email__icontains=busca)
            )
        qs = qs.order_by("usuario__first_name", "usuario__last_name")
        dias = servicos.dias_para_desatualizar(request.user)
        ids = [f.usuario_id for f in qs]
        recorrentes = servicos.recorrencias_de(ids, unidade)
        linhas = [
            {
                "ficha": f,
                "desatualizada": servicos.ficha_desatualizada(f, dias),
                "recorrentes": [r.texto for r in recorrentes.get(f.usuario_id, [])],
            }
            for f in qs
        ]
    return render(
        request,
        "painel/saude_fichas.html",
        {**_contexto_filtros(request, filtros), "linhas": linhas, "busca": busca, "sem_autorizacao": sem_autorizacao},
    )


@never_cache
@sesmt
def ficha_da_pessoa(request, pk):
    """Ficha de uma pessoa, com histórico de versões e linha do tempo de focos. Fica registrado."""
    pessoa = _pessoa_da_unidade(request, pk)
    agora = timezone.now()
    ficha = FichaSaude.objects.filter(usuario=pessoa).first()
    if ficha is not None and not ficha.autoriza_sesmt:
        # Sem autorização não se mostra nada, nem o nome: a pessoa pediu para não ser identificada.
        return render(request, "painel/saude_pessoa.html", {"sem_autorizacao": True})
    servicos.registrar_acesso(request.user, pessoa, AcessoFicha.Finalidade.SESMT_FICHA, agora=agora)
    recorrentes = servicos.recorrencias(pessoa, agora)
    return render(
        request,
        "painel/saude_pessoa.html",
        {
            "pessoa": pessoa,
            "ficha": ficha,
            "secoes": servicos.secoes_da_ficha(None, ficha, recorrentes) if ficha else [],
            "recorrentes": recorrentes,
            "versoes": ficha.versoes.select_related("por") if ficha else [],
            "linha_do_tempo": indicadores.linha_do_tempo(pessoa, agora=agora),
            "situacao": servicos.situacao_da_ficha(pessoa, agora),
        },
    )


@never_cache
@sesmt
def acessos(request):
    """Quem abriu a ficha de quem, e quando."""
    filtros = _filtros(request)
    unidade = filtros["unidade"]
    registros = AcessoFicha.objects.none()
    if unidade:
        inicio, fim = limites(filtros["de"], filtros["ate"])
        registros = AcessoFicha.objects.filter(em__gte=inicio, em__lt=fim).filter(
            Q(colaborador__unidade=unidade) | Q(usuario__unidade=unidade)
        ).select_related("agendamento")
    pagina = Paginator(registros, 50).get_page(request.GET.get("pagina"))
    return render(request, "painel/saude_acessos.html", {**_contexto_filtros(request, filtros), "pagina": pagina})


@never_cache
@sesmt
def csv_agregado(request):
    """Planilha agregada: contagens por região e condição, sem nome. Grupos pequenos escondidos."""
    filtros = _filtros(request)
    if not filtros["unidade"]:
        raise Http404
    dados = indicadores.resumo(filtros["unidade"], filtros["de"], filtros["ate"])
    servicos.registrar_acesso(request.user, None, AcessoFicha.Finalidade.SESMT_AGREGADO)
    resposta, escritor = _csv(f"saude_agregado_{filtros['de']}_{filtros['ate']}.csv")
    escritor.writerow(["Indicador", "Item", "Pessoas"])
    escritor.writerows(indicadores.linhas_agregadas(dados))
    return resposta


@never_cache
@sesmt
def xlsx_fichas(request):
    """Uma linha por ficha: com nome e conteúdo só de quem autorizou; as outras saem sem nome e sem dados."""
    filtros = _filtros(request)
    if not filtros["unidade"]:
        raise Http404
    linhas = indicadores.linhas_individuais(filtros["unidade"])
    servicos.registrar_acesso(request.user, None, AcessoFicha.Finalidade.SESMT_PLANILHA)
    return _xlsx(exportacao.xlsx_fichas(indicadores.CABECALHO_INDIVIDUAL, linhas), "fichas_de_saude.xlsx")
