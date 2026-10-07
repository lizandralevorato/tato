"""Links assinados do lembrete ("Vou" / "Não vou").

O link funciona sem login (a notificação pode ser tocada com o celular
bloqueado), mas só serve para aquele agendamento e expira.
"""

from django.core import signing

SAL = "notificacoes.lembrete"
VALIDADE_SEG = 60 * 60 * 24 * 2


def gerar(agendamento):
    return signing.dumps({"a": agendamento.pk}, salt=SAL, compress=True)


def ler(token):
    """Devolve o id do agendamento ou None se o link for inválido ou velho."""
    try:
        return signing.loads(token, salt=SAL, max_age=VALIDADE_SEG)["a"]
    except (signing.BadSignature, KeyError, TypeError):
        return None
