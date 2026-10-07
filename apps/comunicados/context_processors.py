from .models import Comunicado


def comunicados(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    visiveis = Comunicado.objects.para(usuario)
    return {
        "tem_comunicados": visiveis.exists(),
        "comunicados_nao_lidos": visiveis.exclude(leituras__usuario=usuario).count(),
    }
