"""Regras de negócio da ficha de saúde e da recorrência de regiões.

As views só chamam estas funções. Nada daqui vai para notificações: texto livre de saúde
nunca sai do site.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.agenda import servicos as agenda
from apps.agenda.models import Agendamento
from apps.agenda.servicos import RegraViolada

from . import privacidade
from .models import (
    AcessoFicha,
    ApagamentoFicha,
    ConviteFicha,
    FichaRegiao,
    FichaSaude,
    FichaVersao,
    SugestaoDispensada,
)
from .vocabulario import (
    ALERTAS,
    Condicao,
    Frequencia,
    Intensidade,
    Pressao,
    Regiao,
    lista_em_frase,
    nome_curto_regiao,
    regioes_no_texto,
    regiao_com_artigo,
)

Status = Agendamento.Status

DIAS_SEM_REPETIR_SUGESTAO = 30
DIAS_PADRAO_DESATUALIZADA = 90

# Massoterapeuta: de 2 h antes até 1 h depois do horário do atendimento.
ACESSO_ANTES_MIN = 120
ACESSO_DEPOIS_MIN = 60
# Atendimentos de quem pode ter a ficha aberta (cancelado, liberado e falta ficam de fora).
STATUS_COM_ACESSO = {Status.AGENDADO, Status.CONFIRMADO, Status.CHEGOU, Status.REALIZADO}
# Contam para a recorrência: "realizados ou marcados".
STATUS_QUE_CONTAM = {Status.AGENDADO, Status.CONFIRMADO, Status.CHEGOU, Status.REALIZADO}


# Conteúdo da ficha


def _vazio_dados():
    return {
        "regioes": {},
        "condicoes": [],
        "condicao_outra": "",
        "dor_cronica": False,
        "dor_cronica_descricao": "",
        "problema_coluna": False,
        "problema_coluna_descricao": "",
        "pressao": Pressao.SEM_PREFERENCIA.value,
        "evitar": "",
        "observacoes": "",
        "autoriza_sesmt": False,
    }


def conteudo_da_ficha(ficha) -> dict:
    """Foto da ficha (e usada nas versões). Estrutura estável, só com tipos simples."""
    if ficha is None:
        return _vazio_dados()
    ordem = {valor: i for i, valor in enumerate(Regiao.values)}
    return {
        "regioes": {
            r.regiao: {"intensidade": r.intensidade, "frequencia": r.frequencia}
            for r in sorted(ficha.regioes.all(), key=lambda r: ordem.get(r.regiao, 99))
        },
        "condicoes": sorted(ficha.condicoes),
        "condicao_outra": ficha.condicao_outra,
        "dor_cronica": ficha.dor_cronica,
        "dor_cronica_descricao": ficha.dor_cronica_descricao,
        "problema_coluna": ficha.problema_coluna,
        "problema_coluna_descricao": ficha.problema_coluna_descricao,
        "pressao": ficha.pressao,
        "evitar": ficha.evitar,
        "observacoes": ficha.observacoes,
        "autoriza_sesmt": ficha.autoriza_sesmt,
    }


def _rotulo(enum, valor):
    return enum(valor).label if valor in enum.values else valor


def _descrever_regiao(regiao, dados):
    partes = []
    if dados.get("intensidade"):
        partes.append(f"intensidade {_rotulo(Intensidade, dados['intensidade']).lower()}")
    if dados.get("frequencia"):
        partes.append(f"frequência {_rotulo(Frequencia, dados['frequencia']).lower()}")
    nome = nome_curto_regiao(regiao)
    return f"{nome} ({', '.join(partes)})" if partes else nome


def descrever_mudancas(antes: dict, depois: dict, primeira=False) -> list[str]:
    """O que mudou, em linguagem simples. Textos livres só dizem que mudaram."""
    if primeira:
        return ["Ficha criada."]
    mudancas = []
    for regiao, dados in depois["regioes"].items():
        if regiao not in antes["regioes"]:
            mudancas.append(f"Incluiu região: {_descrever_regiao(regiao, dados)}.")
        elif dados != antes["regioes"][regiao]:
            mudancas.append(f"Mudou a região {_descrever_regiao(regiao, dados)}.")
    for regiao in antes["regioes"]:
        if regiao not in depois["regioes"]:
            mudancas.append(f"Tirou região: {nome_curto_regiao(regiao)}.")
    for condicao in depois["condicoes"]:
        if condicao not in antes["condicoes"]:
            mudancas.append(f"Incluiu condição: {_rotulo(Condicao, condicao).lower()}.")
    for condicao in antes["condicoes"]:
        if condicao not in depois["condicoes"]:
            mudancas.append(f"Tirou condição: {_rotulo(Condicao, condicao).lower()}.")
    rotulos = {
        "condicao_outra": "outra condição",
        "dor_cronica": "dor crônica",
        "dor_cronica_descricao": "descrição da dor crônica",
        "problema_coluna": "problema na coluna",
        "problema_coluna_descricao": "descrição do problema na coluna",
        "evitar": "o que evitar",
        "observacoes": "observações gerais",
    }
    for campo, nome in rotulos.items():
        if antes[campo] != depois[campo]:
            mudancas.append(f"Mudou {nome}.")
    if antes["pressao"] != depois["pressao"]:
        mudancas.append(f"Mudou a preferência de pressão para {_rotulo(Pressao, depois['pressao']).lower()}.")
    if antes["autoriza_sesmt"] != depois["autoriza_sesmt"]:
        mudancas.append(
            "Autorizou o SESMT a ver a ficha com o nome." if depois["autoriza_sesmt"]
            else "Retirou a autorização do SESMT."
        )
    return mudancas


def _normalizar(dados: dict) -> dict:
    limpo = _vazio_dados()
    limpo.update({k: v for k, v in dados.items() if k in limpo})
    limpo["regioes"] = {
        slug: {"intensidade": (d or {}).get("intensidade", ""), "frequencia": (d or {}).get("frequencia", "")}
        for slug, d in dados.get("regioes", {}).items()
        if slug in Regiao.values
    }
    limpo["condicoes"] = sorted({c for c in dados.get("condicoes", []) if c in Condicao.values})
    if limpo["pressao"] not in Pressao.values:
        limpo["pressao"] = Pressao.SEM_PREFERENCIA.value
    for campo in ("condicao_outra", "dor_cronica_descricao", "problema_coluna_descricao", "evitar", "observacoes"):
        limpo[campo] = (limpo[campo] or "").strip()
    limpo["dor_cronica"] = bool(limpo["dor_cronica"])
    limpo["problema_coluna"] = bool(limpo["problema_coluna"])
    limpo["autoriza_sesmt"] = bool(limpo["autoriza_sesmt"])
    return limpo


def precisa_consentir(ficha) -> bool:
    """Ficha nova, ou texto de privacidade que mudou desde o último aceite."""
    return ficha is None or ficha.consentimento_versao != privacidade.VERSAO_TEXTO


def salvar_ficha(usuario, dados: dict, consentimento: bool, agora=None):
    """Cria ou atualiza a ficha e grava uma versão imutável. Devolve (ficha, versao)."""
    agora = agora or timezone.now()
    if usuario.eh_massoterapeuta:
        raise RegraViolada("Massoterapeutas não têm ficha de saúde.")
    novo = _normalizar(dados)
    with transaction.atomic():
        ficha = FichaSaude.objects.select_for_update().filter(usuario=usuario).first()
        if precisa_consentir(ficha) and not consentimento:
            raise RegraViolada("Para salvar a ficha, marque que você leu e aceita o aviso de privacidade.")
        antes = conteudo_da_ficha(ficha)
        primeira = ficha is None
        if primeira:
            ficha = FichaSaude(usuario=usuario, criada_em=agora)
        if consentimento and precisa_consentir(None if primeira else ficha):
            ficha.consentimento_em = agora
            ficha.consentimento_versao = privacidade.VERSAO_TEXTO
        for campo in (
            "condicao_outra", "dor_cronica", "dor_cronica_descricao", "problema_coluna",
            "problema_coluna_descricao", "pressao", "evitar", "observacoes", "autoriza_sesmt",
        ):
            setattr(ficha, campo, novo[campo])
        ficha.condicoes = novo["condicoes"]
        ficha.atualizada_em = agora
        ficha.save()
        ficha.regioes.exclude(regiao__in=novo["regioes"]).delete()
        for slug, d in novo["regioes"].items():
            FichaRegiao.objects.update_or_create(
                ficha=ficha, regiao=slug, defaults={"intensidade": d["intensidade"], "frequencia": d["frequencia"]}
            )
        mudancas = descrever_mudancas(antes, novo, primeira)
        ultimo = ficha.versoes.order_by("-numero").values_list("numero", flat=True).first() or 0
        versao = FichaVersao.objects.create(
            ficha=ficha, numero=ultimo + 1, por=usuario, em=agora, mudancas=mudancas, conteudo=novo
        )
    return ficha, versao


def apagar_ficha(usuario, apagar_observacoes=False, agora=None) -> bool:
    """Apaga a ficha e as versões. Fica só o registro de que foi apagada, sem dado de saúde."""
    agora = agora or timezone.now()
    with transaction.atomic():
        ficha = FichaSaude.objects.filter(usuario=usuario).first()
        if ficha is None:
            return False
        ficha.delete()
        ApagamentoFicha.objects.create(colaborador=usuario, colaborador_nome=usuario.nome, em=agora)
        if apagar_observacoes:
            usuario.agendamentos.update(foco_regioes=[], observacao="", observacao_em=None)
    return True


# Situação (o administrador só vê isto, nunca o conteúdo)


def dias_para_desatualizar(usuario) -> int:
    if usuario.unidade_id:
        return agenda.politica_da(usuario.unidade).ficha_desatualizada_dias
    return DIAS_PADRAO_DESATUALIZADA


def ficha_desatualizada(ficha, dias: int, agora=None) -> bool:
    agora = agora or timezone.now()
    return bool(ficha and dias > 0 and agora - ficha.atualizada_em > timedelta(days=dias))


def situacao_da_ficha(usuario, agora=None) -> dict:
    """Existe? Está atualizada? Sem nenhum conteúdo de saúde."""
    ficha = FichaSaude.objects.filter(usuario=usuario).only("atualizada_em").first()
    desatualizada = ficha_desatualizada(ficha, dias_para_desatualizar(usuario), agora)
    if ficha is None:
        rotulo = "Não preenchida"
    elif desatualizada:
        rotulo = f"Preenchida, desatualizada (última atualização em {ficha.atualizada_em:%d/%m/%Y})"
    else:
        rotulo = f"Preenchida e atualizada (em {ficha.atualizada_em:%d/%m/%Y})"
    return {
        "existe": ficha is not None,
        "desatualizada": desatualizada,
        "atualizada_em": ficha.atualizada_em if ficha else None,
        "rotulo": rotulo,
        "texto": f"Ficha de saúde: {rotulo[0].lower()}{rotulo[1:]}.",
    }


def situacoes_por_usuario(usuario_ids, dias: int, agora=None) -> dict:
    """Mesmo que `situacao_da_ficha`, para várias pessoas de uma vez (lista de Pessoas)."""
    agora = agora or timezone.now()
    fichas = dict(FichaSaude.objects.filter(usuario_id__in=usuario_ids).values_list("usuario_id", "atualizada_em"))
    resultado = {}
    for uid in usuario_ids:
        em = fichas.get(uid)
        if em is None:
            resultado[uid] = "Sem ficha"
        elif dias > 0 and agora - em > timedelta(days=dias):
            resultado[uid] = "Ficha desatualizada"
        else:
            resultado[uid] = "Ficha atualizada"
    return resultado


# Convite e lembrete


def convite_a_mostrar(usuario, agora=None):
    """"primeira" (convite), "desatualizada" (lembrete) ou None. Marca como mostrado."""
    agora = agora or timezone.now()
    if usuario.eh_massoterapeuta:
        return None
    ficha = FichaSaude.objects.filter(usuario=usuario).only("atualizada_em").first()
    convite, _ = ConviteFicha.objects.get_or_create(usuario=usuario)
    if ficha is None:
        if convite.convite_em is not None:
            return None
        convite.convite_em = agora
        convite.save(update_fields=["convite_em"])
        return "primeira"
    dias = dias_para_desatualizar(usuario)
    if not ficha_desatualizada(ficha, dias, agora):
        return None
    ultimo = max(filter(None, [ficha.atualizada_em, convite.lembrete_em]))
    if agora - ultimo <= timedelta(days=dias):
        return None
    convite.lembrete_em = agora
    convite.save(update_fields=["lembrete_em"])
    return "desatualizada"


# Recorrência: o sistema conta, a pessoa não precisa contar nada


@dataclass(frozen=True)
class Recorrencia:
    """Uma região que apareceu várias vezes nos pedidos de uma pessoa. É um sinal, não um diagnóstico."""

    regiao: str
    vezes: int
    janela_dias: int
    apenas_texto: bool = False  # só passou do limite somando menções no texto livre

    @property
    def texto(self):
        nome = nome_curto_regiao(self.regiao)
        if self.apenas_texto:
            return f"Região também mencionada no texto: {nome} ({self.vezes}x em {self.janela_dias} dias)"
        return f"Região recorrente: {nome} ({self.vezes}x em {self.janela_dias} dias)"


def parametros_de_recorrencia(unidade):
    """(janela em dias, limite). Limite 0 desliga."""
    if unidade is None:
        return 30, 3
    politica = agenda.politica_da(unidade)
    return politica.recorrencia_janela_dias, politica.recorrencia_limite


def recorrencias_de(colaborador_ids, unidade, agora=None) -> dict:
    """Regiões recorrentes de várias pessoas de uma vez: {id: [Recorrencia, ...]}.

    Conta, por pessoa, em quantos agendamentos realizados ou marcados dentro da janela cada região
    aparece. A fonte principal é o foco escolhido (campo estruturado). As palavras do texto livre
    só servem de apoio: nunca viram "recorrente" sozinhas, só somam quando o limite seria atingido.
    """
    agora = agora or timezone.now()
    janela, limite = parametros_de_recorrencia(unidade)
    resultado = {cid: [] for cid in colaborador_ids}
    if limite <= 0 or not colaborador_ids:
        return resultado
    estruturado = {cid: Counter() for cid in colaborador_ids}
    texto = {cid: Counter() for cid in colaborador_ids}
    linhas = Agendamento.objects.filter(
        colaborador_id__in=colaborador_ids,
        status__in=STATUS_QUE_CONTAM,
        inicio__gte=agora - timedelta(days=janela),
    ).values_list("colaborador_id", "foco_regioes", "observacao")
    for cid, foco, observacao in linhas:
        foco = set(foco or [])
        estruturado[cid].update(foco)
        # Cada agendamento conta uma vez por região: o que já veio do foco não soma de novo.
        texto[cid].update(set(regioes_no_texto(observacao)) - foco)
    for cid in colaborador_ids:
        for regiao in Regiao.values:
            principal = estruturado[cid][regiao]
            if principal >= limite:
                resultado[cid].append(Recorrencia(regiao, principal, janela))
            elif principal + texto[cid][regiao] >= limite:
                resultado[cid].append(Recorrencia(regiao, principal + texto[cid][regiao], janela, apenas_texto=True))
        resultado[cid].sort(key=lambda r: (r.apenas_texto, -r.vezes))
    return resultado


def recorrencias(colaborador, agora=None) -> list:
    return recorrencias_de([colaborador.pk], colaborador.unidade, agora)[colaborador.pk]


# Sugestão de pôr a região na ficha (a pessoa decide; a ficha nunca muda sozinha)


def sugestoes_para(colaborador, agora=None) -> list[str]:
    """Regiões recorrentes (pelo foco escolhido) que ainda não estão na ficha nem foram dispensadas há pouco."""
    agora = agora or timezone.now()
    candidatas = [r.regiao for r in recorrencias(colaborador, agora) if not r.apenas_texto]
    if not candidatas:
        return []
    na_ficha = set(FichaRegiao.objects.filter(ficha__usuario=colaborador).values_list("regiao", flat=True))
    dispensadas = set(
        SugestaoDispensada.objects.filter(
            colaborador=colaborador, em__gt=agora - timedelta(days=DIAS_SEM_REPETIR_SUGESTAO)
        ).values_list("regiao", flat=True)
    )
    return [r for r in candidatas if r not in na_ficha and r not in dispensadas]


def sugestoes_para_tela(colaborador, agora=None) -> list[dict]:
    """`sugestoes_para` já com os textos prontos para o template."""
    return [
        {"slug": slug, "nome": nome_curto_regiao(slug), "com_artigo": regiao_com_artigo(slug)}
        for slug in sugestoes_para(colaborador, agora)
    ]


def dispensar_sugestao(colaborador, regiao: str, agora=None):
    """"Agora não": não repete a sugestão dessa região por 30 dias."""
    if regiao not in Regiao.values:
        raise RegraViolada("Região desconhecida.")
    return SugestaoDispensada.objects.create(colaborador=colaborador, regiao=regiao, em=agora or timezone.now())


# Massoterapeuta: acesso à ficha, uma pessoa por vez


def janela_de_acesso(agendamento):
    """De 2 h antes até 1 h depois do horário do atendimento."""
    return (
        agendamento.inicio - timedelta(minutes=ACESSO_ANTES_MIN),
        agendamento.inicio + timedelta(minutes=ACESSO_DEPOIS_MIN),
    )


def na_janela_de_acesso(agendamento, agora=None) -> bool:
    agora = agora or timezone.now()
    abre, fecha = janela_de_acesso(agendamento)
    return agendamento.status in STATUS_COM_ACESSO and abre <= agora <= fecha


def pode_abrir_ficha(usuario, agendamento, agora=None) -> bool:
    """Só o massoterapeuta do atendimento, e só dentro da janela."""
    return agendamento.massoterapeuta.usuario_id == usuario.pk and na_janela_de_acesso(agendamento, agora)


ALERTAS_VALORES = frozenset(c.value for c in ALERTAS)


def resumos_da_agenda(agendamentos, unidade, agora=None) -> dict:
    """Resumo curto de cada atendimento da lista do dia: {pk do agendamento: dict}.

    É só um ponteiro: foco e pedido da sessão, região recorrente e se a ficha tem alertas. O conteúdo da
    ficha nunca vai na lista; ele só aparece na página da ficha, aberta pelo massoterapeuta.
    """
    agora = agora or timezone.now()
    agendamentos = list(agendamentos)
    ids = list({ag.colaborador_id for ag in agendamentos})
    fichas = dict(FichaSaude.objects.filter(usuario_id__in=ids).values_list("usuario_id", "condicoes"))
    recorrentes = recorrencias_de(ids, unidade, agora)
    resumos = {}
    for ag in agendamentos:
        na_janela = na_janela_de_acesso(ag, agora)
        tem_ficha = ag.colaborador_id in fichas
        foco = lista_em_frase([nome_curto_regiao(s) for s in ag.foco_regioes or []])
        regioes_recorrentes = [r.texto for r in recorrentes.get(ag.colaborador_id, [])]
        tem_alertas = bool(tem_ficha and na_janela and ALERTAS_VALORES & set(fichas[ag.colaborador_id]))
        frases = []
        if foco:
            frases.append(f"Foco hoje: {foco}.")
        frases.extend(f"{texto}." for texto in regioes_recorrentes)
        if ag.observacao:
            frases.append(f"Pedido da pessoa: “{ag.observacao}”.")
        if tem_alertas:
            frases.append("A ficha tem alertas de atenção. Abra a ficha antes de começar.")
        resumos[ag.pk] = {
            "foco": foco,
            "frases": frases,
            "tem_ficha": tem_ficha,
            "pode_ver_ficha": tem_ficha and na_janela,
            "ficha_abre_em": (
                janela_de_acesso(ag)[0]
                if tem_ficha and agora < janela_de_acesso(ag)[0] and ag.status in STATUS_COM_ACESSO
                else None
            ),
            "tem_alertas": tem_alertas,
        }
    return resumos


@dataclass
class Secao:
    titulo: str
    frases: list


def _lista_de(valores, enum):
    return [enum(v).label if v in enum.values else v for v in valores]


def secoes_da_ficha(agendamento, ficha, recorrentes=()) -> list[Secao]:
    """O que o massoterapeuta lê (e ouve) na página da ficha, na ordem certa.

    Alertas de atenção, foco da sessão (com o pedido da pessoa para esta massagem), regiões recorrentes,
    regiões de dor, outras informações de saúde, pressão, o que evitar e observações. A ficha aparece
    sempre inteira: o pedido da sessão é um acréscimo, nunca um recorte.
    """
    conteudo = conteudo_da_ficha(ficha)
    secoes = []

    alertas = [c for c in conteudo["condicoes"] if c in ALERTAS_VALORES]
    secoes.append(
        Secao(
            "Alertas de atenção",
            [f"Atenção: {rotulo.lower()}." for rotulo in _lista_de(alertas, Condicao)] or ["Nenhum alerta de atenção informado."],
        )
    )

    foco = lista_em_frase([nome_curto_regiao(s) for s in (agendamento.foco_regioes if agendamento else None) or []])
    if agendamento is not None:
        frases = []
        frases.append(f"Foco desta sessão: {foco}." if foco else "A pessoa não escolheu foco para esta sessão.")
        if agendamento.observacao:
            frases.append(f"Pedido da pessoa para esta sessão: {agendamento.observacao}")
        secoes.append(Secao("Foco desta sessão", frases))

    if recorrentes:
        secoes.append(Secao("Regiões recorrentes", [f"{r.texto}." for r in recorrentes]))

    regioes = [
        f"{nome_curto_regiao(slug).capitalize()}: {', '.join(_partes_regiao(d)) or 'sem detalhes'}."
        for slug, d in conteudo["regioes"].items()
    ]
    secoes.append(Secao("Regiões com dor ou desconforto", regioes or ["Nenhuma região informada."]))

    outras = []
    comuns = [c for c in conteudo["condicoes"] if c not in ALERTAS_VALORES]
    if comuns:
        outras.append(f"Condições: {lista_em_frase([r.lower() for r in _lista_de(comuns, Condicao)])}.")
    if conteudo["condicao_outra"]:
        outras.append(f"Outra condição: {conteudo['condicao_outra']}.")
    if conteudo["dor_cronica"]:
        outras.append("Dor crônica: sim." + (f" {conteudo['dor_cronica_descricao']}" if conteudo["dor_cronica_descricao"] else ""))
    if conteudo["problema_coluna"]:
        outras.append("Problema na coluna: sim." + (f" {conteudo['problema_coluna_descricao']}" if conteudo["problema_coluna_descricao"] else ""))
    if outras:
        secoes.append(Secao("Outras informações de saúde", outras))

    pressao = Pressao(conteudo["pressao"]) if conteudo["pressao"] in Pressao.values else Pressao.SEM_PREFERENCIA
    secoes.append(
        Secao(
            "Preferência de pressão",
            ["Sem preferência de pressão."] if pressao == Pressao.SEM_PREFERENCIA else [f"Prefere pressão {pressao.label.lower()}."],
        )
    )
    if conteudo["evitar"]:
        secoes.append(Secao("O que evitar", [f"Evitar: {conteudo['evitar']}"]))
    if conteudo["observacoes"]:
        secoes.append(Secao("Observações", [conteudo["observacoes"]]))
    return secoes


def _partes_regiao(dados):
    partes = []
    if dados.get("intensidade"):
        partes.append(f"intensidade {_rotulo(Intensidade, dados['intensidade']).lower()}")
    if dados.get("frequencia"):
        partes.append(f"frequência {_rotulo(Frequencia, dados['frequencia']).lower()}")
    return partes


# Registro de acesso


def registrar_acesso(usuario, colaborador, finalidade, agendamento=None, agora=None):
    return AcessoFicha.objects.create(
        usuario=usuario,
        usuario_nome=usuario.nome,
        colaborador=colaborador,
        colaborador_nome=colaborador.nome if colaborador else "",
        agendamento=agendamento,
        finalidade=finalidade,
        em=agora or timezone.now(),
    )
