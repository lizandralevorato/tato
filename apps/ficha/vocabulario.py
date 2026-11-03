"""Vocabulário único da ficha, da observação do agendamento e do painel.

Não importa nenhum modelo, para a agenda poder usar sem criar ciclo entre os apps.
"""

import re
import unicodedata

from django.db import models


class Regiao(models.TextChoices):
    CABECA_MANDIBULA = "cabeca_mandibula", "Cabeça e mandíbula"
    PESCOCO = "pescoco", "Pescoço"
    OMBROS = "ombros", "Ombros"
    COSTAS_ALTAS = "costas_altas", "Parte alta das costas"
    LOMBAR = "lombar", "Lombar (parte baixa das costas)"
    BRACOS_COTOVELOS = "bracos_cotovelos", "Braços e cotovelos"
    PUNHOS_MAOS = "punhos_maos", "Punhos e mãos"
    QUADRIL = "quadril", "Quadril"
    PERNAS = "pernas", "Pernas"
    JOELHOS = "joelhos", "Joelhos"
    PES = "pes", "Pés"


class Intensidade(models.TextChoices):
    LEVE = "leve", "Leve"
    MODERADA = "moderada", "Moderada"
    FORTE = "forte", "Forte"


class Frequencia(models.TextChoices):
    AS_VEZES = "as_vezes", "Às vezes"
    FREQUENTE = "frequente", "Frequente"
    SEMPRE = "sempre", "Sempre"


class Pressao(models.TextChoices):
    LEVE = "leve", "Leve"
    MEDIA = "media", "Média"
    FIRME = "firme", "Firme"
    SEM_PREFERENCIA = "sem_preferencia", "Sem preferência"


class Condicao(models.TextChoices):
    HERNIA_DISCO = "hernia_disco", "Hérnia de disco"
    ESCOLIOSE = "escoliose", "Escoliose (coluna torta)"
    FIBROMIALGIA = "fibromialgia", "Fibromialgia"
    LER_DORT = "ler_dort", "LER/DORT ou tendinite (dor por esforço repetido)"
    ENXAQUECA = "enxaqueca", "Enxaqueca"
    HIPERTENSAO = "hipertensao", "Pressão alta (hipertensão)"
    DIABETES = "diabetes", "Diabetes"
    OSTEOPOROSE = "osteoporose", "Osteoporose (ossos frágeis)"
    GESTACAO = "gestacao", "Gestação (gravidez)"
    TROMBOSE_VARIZES = "trombose_varizes", "Trombose ou varizes severas"
    ANTICOAGULANTE = "anticoagulante", "Uso de anticoagulante (remédio que afina o sangue)"
    CIRURGIA_RECENTE = "cirurgia_recente", "Cirurgia recente"
    LESAO_RECENTE = "lesao_recente", "Lesão recente"
    ALERGIA_OLEOS = "alergia_oleos", "Alergia a óleos ou cremes"


# Condições que pedem cuidado do massoterapeuta e aparecem primeiro na ficha.
# É uma decisão clínica: o SESMT deve validar esta lista.
ALERTAS = frozenset(
    {
        Condicao.GESTACAO,
        Condicao.ANTICOAGULANTE,
        Condicao.TROMBOSE_VARIZES,
        Condicao.CIRURGIA_RECENTE,
        Condicao.LESAO_RECENTE,
        Condicao.OSTEOPOROSE,
        Condicao.ALERGIA_OLEOS,
    }
)

# Palavras (sem acento, minúsculas) que indicam a região no texto livre. Só apoio:
# o campo estruturado é a fonte principal.
SINONIMOS = {
    Regiao.CABECA_MANDIBULA: ["cabeca", "mandibula", "maxilar", "queixo", "face", "rosto"],
    Regiao.PESCOCO: ["pescoco", "cervical", "nuca"],
    Regiao.OMBROS: ["ombro", "ombros", "trapezio", "trapezios"],
    Regiao.COSTAS_ALTAS: ["costas", "dorsal", "escapula", "escapulas", "omoplata", "omoplatas"],
    Regiao.LOMBAR: ["lombar", "lombares", "lombalgia", "baixa das costas"],
    Regiao.BRACOS_COTOVELOS: ["braco", "bracos", "cotovelo", "cotovelos", "antebraco", "antebracos", "biceps", "triceps"],
    Regiao.PUNHOS_MAOS: ["punho", "punhos", "mao", "maos", "dedo", "dedos"],
    Regiao.QUADRIL: ["quadril", "quadris", "bacia", "gluteo", "gluteos"],
    Regiao.PERNAS: ["perna", "pernas", "coxa", "coxas", "panturrilha", "panturrilhas"],
    Regiao.JOELHOS: ["joelho", "joelhos"],
    Regiao.PES: ["pe", "pes", "calcanhar", "calcanhares", "tornozelo", "tornozelos"],
}

_PADROES = {
    regiao: re.compile(r"\b(?:" + "|".join(re.escape(p) for p in palavras) + r")\b")
    for regiao, palavras in SINONIMOS.items()
}


def sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in base if not unicodedata.combining(c)).lower()


def regioes_no_texto(texto: str) -> list[str]:
    """Regiões citadas no texto livre, sem acento e sem diferenciar maiúsculas."""
    normal = sem_acento(texto)
    return [regiao.value for regiao, padrao in _PADROES.items() if padrao.search(normal)]


def rotulo_regiao(slug: str) -> str:
    return Regiao(slug).label if slug in Regiao.values else slug


def nome_curto_regiao(slug: str) -> str:
    """Para frases: "ombros", "lombar", "parte alta das costas"."""
    return {Regiao.LOMBAR.value: "lombar"}.get(slug) or rotulo_regiao(slug).lower()


_COM_ARTIGO = {
    Regiao.CABECA_MANDIBULA: "na cabeça e mandíbula",
    Regiao.PESCOCO: "no pescoço",
    Regiao.OMBROS: "nos ombros",
    Regiao.COSTAS_ALTAS: "na parte alta das costas",
    Regiao.LOMBAR: "na lombar",
    Regiao.BRACOS_COTOVELOS: "nos braços e cotovelos",
    Regiao.PUNHOS_MAOS: "nos punhos e mãos",
    Regiao.QUADRIL: "no quadril",
    Regiao.PERNAS: "nas pernas",
    Regiao.JOELHOS: "nos joelhos",
    Regiao.PES: "nos pés",
}


def regiao_com_artigo(slug: str) -> str:
    """Para frases como "foco nos ombros"."""
    return _COM_ARTIGO.get(slug) or f"em {nome_curto_regiao(slug)}"


def lista_em_frase(itens: list[str]) -> str:
    """["ombros", "pescoço", "lombar"] -> "ombros, pescoço e lombar"."""
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]
