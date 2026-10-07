from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import EntrarForm, PreferenciasForm
from .models import PerfilAcessibilidade


class EntrarView(auth_views.LoginView):
    template_name = "contas/entrar.html"
    authentication_form = EntrarForm
    redirect_authenticated_user = True


def _destino_seguro(request, padrao="inicio"):
    destino = request.POST.get("proximo") or request.GET.get("proximo")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return padrao


@login_required
def preferencias(request):
    perfil, _ = PerfilAcessibilidade.objects.get_or_create(usuario=request.user)
    primeiro_acesso = not perfil.configurado

    if request.method == "POST":
        if "pular" in request.POST:
            perfil.configurado = True
            perfil.save(update_fields=["configurado", "atualizado_em"])
            messages.info(request, "Tudo bem. Você pode ajustar o site depois em Preferências.")
            return redirect(_destino_seguro(request))

        form = PreferenciasForm(request.POST, instance=perfil)
        if form.is_valid():
            perfil = form.save(commit=False)
            perfil.configurado = True
            perfil.save()
            messages.success(request, "Preferências salvas.")
            return redirect(_destino_seguro(request, padrao="contas:preferencias"))
    else:
        form = PreferenciasForm(instance=perfil)

    return render(
        request,
        "contas/preferencias.html",
        {
            "form": form,
            "primeiro_acesso": primeiro_acesso,
            "proximo": request.GET.get("proximo", ""),
        },
    )
