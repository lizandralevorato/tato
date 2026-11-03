"""Números da ficha de saúde para o painel do SESMT.

Tudo aqui é de uso exclusivo do SESMT (a permissão é verificada nas views). As contagens agregadas
saem em planilha com grupos pequenos escondidos; ver `suprimir`.
"""

from collections import Counter
from datetime import date, timedelta

from django.utils import timezone

from apps.agenda import servicos as agenda
from apps.agenda.models import Agendamento
from apps.contas.models import Usuario
from apps.painel import indicadores as painel

from . import servicos
from .models import FichaRegiao, FichaSaude
from .vocabulario import Condicao, Frequencia, Intensidade, Pressao, Regiao

# Em planilha, grupos com menos pessoas que isto viram "menos de 3" (evita apontar uma pessoa).
GRUPO_MINIMO = 3


def suprimir(valor: int):
    return valor if valor >= GRUPO_MINIMO else f"menos de {GRUPO_MINIMO}"


def colaboradores_da_unidade(unidade):
    return Usuario.objects.filter(unidade=unidade, is_active=True).exclude(papel=Usuario.Papel.MASSOTERAPEUTA)


def resumo(unidade, de: date, ate: date, agora=None):
    agora = agora or timezone.now()
    pessoas = list(colaboradores_da_unidade(unidade))
    ids = [p.pk for p in pessoas]
    dias = agenda.politica_da(unidade).ficha_desatualizada_dias
    fichas = list(FichaSaude.objects.filter(usuario_id__in=ids))
    inicio, fim = painel.limites(de, ate)

    desatualizadas = sum(1 for f in fichas if servicos.ficha_desatualizada(f, dias, agora))
    atualizadas_no_periodo = sum(1 for f in fichas if inicio <= f.atualizada_em < fim)

    na_ficha = Counter()
    fortes = Counter()
    frequentes = Counter()
    for linha in FichaRegiao.objects.filter(ficha__usuario_id__in=ids):
        na_ficha[linha.regiao] += 1
        if linha.intensidade == Intensidade.FORTE:
            fortes[linha.regiao] += 1
        if linha.frequencia in (Frequencia.FREQUENTE, Frequencia.SEMPRE):
            frequentes[linha.regiao] += 1

    focos = Counter()
    pedidos = Agendamento.objects.filter(
        colaborador_id__in=ids, status__in=servicos.STATUS_QUE_CONTAM, inicio__gte=inicio, inicio__lt=fim
    ).values_list("foco_regioes", flat=True)
    for foco in pedidos:
        focos.update(set(foco or []))

    condicoes = Counter()
    for ficha in fichas:
        condicoes.update(set(ficha.condicoes))

    ranking = sorted(
        (
            {
                "regiao": r.value,
                "nome": r.label,
                "fichas": na_ficha[r.value],
                "fortes": fortes[r.value],
                "frequentes": frequentes[r.value],
                "focos": focos[r.value],
            }
            for r in Regiao
        ),
        key=lambda linha: (-linha["fichas"], -linha["focos"], linha["nome"]),
    )
    ranking_condicoes = sorted(
        ({"slug": c.value, "nome": c.label, "pessoas": condicoes[c.value]} for c in Condicao),
        key=lambda linha: (-linha["pessoas"], linha["nome"]),
    )

    por_id = {p.pk: p for p in pessoas}
    autorizados = {f.usuario_id for f in fichas if f.autoriza_sesmt}
    recorrentes = []
    total_recorrentes = 0
    for cid, itens in servicos.recorrencias_de(ids, unidade, agora).items():
        if itens:
            total_recorrentes += 1
            # Nome só de quem autorizou o SESMT; os demais entram apenas na contagem.
            if cid in autorizados:
                recorrentes.append({"pessoa": por_id[cid], "itens": itens})
    recorrentes.sort(key=lambda linha: linha["pessoa"].nome.casefold())

    return {
        "pessoas": len(pessoas),
        "preenchidas": len(fichas),
        "desatualizadas": desatualizadas,
        "atualizadas_no_periodo": atualizadas_no_periodo,
        "ranking": ranking,
        "maior_ranking": max((linha["fichas"] for linha in ranking), default=0) or 1,
        "condicoes": ranking_condicoes,
        "recorrentes": recorrentes,
        "total_recorrentes": total_recorrentes,
        "dias_desatualizada": dias,
    }


def linhas_agregadas(dados) -> list[list]:
    """Linhas da planilha agregada: sem nome e com grupos pequenos escondidos."""
    linhas = [
        ["Pessoas na unidade", "", dados["pessoas"]],
        ["Fichas preenchidas", "", suprimir(dados["preenchidas"])],
        ["Fichas desatualizadas", "", suprimir(dados["desatualizadas"])],
        ["Pessoas com região recorrente", "", suprimir(dados["total_recorrentes"])],
    ]
    for linha in dados["ranking"]:
        linhas.append(["Região com dor (fichas)", linha["nome"], suprimir(linha["fichas"])])
    for linha in dados["ranking"]:
        linhas.append(["Região pedida como foco (massagens no período)", linha["nome"], suprimir(linha["focos"])])
    for linha in dados["condicoes"]:
        linhas.append(["Condição de saúde", linha["nome"], suprimir(linha["pessoas"])])
    return linhas


NAO_DIZ = "Prefere não dizer"
NAO_AUTORIZADO = "Não autorizado"
CABECALHO_INDIVIDUAL = [
    "Pessoa", "E-mail", "Última atualização", "Regiões com dor", "Condições", "Outra condição", "Dor crônica",
    "Dor crônica (descrição)", "Problema na coluna", "Problema na coluna (descrição)", "Pressão preferida",
    "Evitar", "Observações",
]


def linhas_individuais(unidade) -> list[list]:
    """Uma linha por ficha da unidade. Sem a autorização da pessoa, nome e conteúdo não saem."""
    pessoas = colaboradores_da_unidade(unidade)
    fichas = (
        FichaSaude.objects.filter(usuario__in=pessoas)
        .select_related("usuario")
        .prefetch_related("regioes")
        .order_by("usuario__first_name", "usuario__last_name")
    )
    autorizadas, outras = [], []
    for ficha in fichas:
        if not ficha.autoriza_sesmt:
            outras.append([NAO_DIZ, NAO_DIZ, NAO_DIZ] + [NAO_AUTORIZADO] * (len(CABECALHO_INDIVIDUAL) - 3))
            continue
        c = servicos.conteudo_da_ficha(ficha)
        pressao = c["pressao"]
        autorizadas.append(
            [
                ficha.usuario.nome,
                ficha.usuario.email,
                timezone.localtime(ficha.atualizada_em).strftime("%d/%m/%Y"),
                "; ".join(servicos._descrever_regiao(slug, d).capitalize() for slug, d in c["regioes"].items()),
                "; ".join(servicos._lista_de(c["condicoes"], Condicao)),
                c["condicao_outra"],
                "Sim" if c["dor_cronica"] else "Não",
                c["dor_cronica_descricao"],
                "Sim" if c["problema_coluna"] else "Não",
                c["problema_coluna_descricao"],
                servicos._rotulo(Pressao, pressao),
                c["evitar"],
                c["observacoes"],
            ]
        )
    return autorizadas + outras


def linha_do_tempo(colaborador, limite_dias=365, agora=None):
    """Focos e observações das massagens da pessoa, do mais recente para o mais antigo."""
    agora = agora or timezone.now()
    return list(
        Agendamento.objects.filter(
            colaborador=colaborador, status__in=servicos.STATUS_QUE_CONTAM, inicio__gte=agora - timedelta(days=limite_dias)
        )
        .select_related("massoterapeuta__usuario")
        .order_by("-inicio")
    )
