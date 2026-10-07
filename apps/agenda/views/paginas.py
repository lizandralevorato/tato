from django.shortcuts import render

from .. import servicos
from ..models import PoliticaBeneficio, Unidade


def _duracao_texto(minutos):
    horas, resto = divmod(minutos, 60)
    if horas and resto:
        return f"{horas} hora{'s' if horas > 1 else ''} e {resto} minutos"
    if horas:
        return f"{horas} hora{'s' if horas > 1 else ''}"
    return f"{minutos} minutos"


def como_funciona(request):
    """Página pública, para divulgar o benefício."""
    unidade = None
    if request.user.is_authenticated and request.user.unidade_id:
        unidade = request.user.unidade
    else:
        unidade = Unidade.objects.filter(ativa=True).first()
    politica = servicos.politica_da(unidade) if unidade else PoliticaBeneficio()
    massoterapeuta = unidade.massoterapeutas.filter(ativo=True).first() if unidade else None
    return render(
        request,
        "como_funciona.html",
        {
            "politica": politica,
            "duracao": massoterapeuta.duracao_sessao_min if massoterapeuta else 20,
            "checkin_abre": _duracao_texto(max(politica.checkin_abre_min, politica.checkin_prazo_min)),
            "checkin_prazo": _duracao_texto(politica.checkin_prazo_min),
        },
    )
