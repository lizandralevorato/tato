from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse

from apps.contas.models import PerfilAcessibilidade, Usuario


@login_required
def inicio(request):
    """Leva cada pessoa para a tela principal do seu papel.

    No primeiro acesso, passa antes pelas preferências de acessibilidade.
    """
    perfil, _ = PerfilAcessibilidade.objects.get_or_create(usuario=request.user)
    papel = request.user.papel
    if papel == Usuario.Papel.MASSOTERAPEUTA:
        destino = reverse("agenda:agora")
    elif papel == Usuario.Papel.GESTAO:
        destino = reverse("painel:inicio")
    elif request.user.eh_equipe:
        destino = reverse("agenda:recepcao")
    else:
        destino = reverse("agenda:meus_agendamentos")

    if not perfil.configurado:
        return redirect(f"{reverse('contas:preferencias')}?proximo={destino}")
    return redirect(destino)
