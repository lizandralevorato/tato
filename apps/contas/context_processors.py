from .models import PerfilAcessibilidade


def acessibilidade(request):
    """Disponibiliza as preferências de acessibilidade em todos os templates.

    Visitantes sem login recebem o perfil padrão (segue o tema do sistema).
    """
    usuario = getattr(request, "user", None)
    if usuario is not None and usuario.is_authenticated:
        perfil, _ = PerfilAcessibilidade.objects.get_or_create(usuario=usuario)
    else:
        perfil = PerfilAcessibilidade()
    return {"perfil_a11y": perfil}
