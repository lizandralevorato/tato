from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.agenda.servicos import RegraViolada

from .. import privacidade, servicos
from ..forms import FichaForm
from ..models import AcessoFicha, FichaSaude
from ..permissoes import dono_da_ficha
from ..vocabulario import nome_curto_regiao


def _destino(request):
    destino = request.POST.get("proximo") or request.GET.get("proximo")
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        return destino
    return ""


@never_cache
@dono_da_ficha
def minha_ficha(request):
    """Criar ou editar a própria ficha, em 3 etapas (todas na mesma página, sem JS)."""
    ficha = FichaSaude.objects.filter(usuario=request.user).first()
    exige = servicos.precisa_consentir(ficha)
    proximo = _destino(request)
    if request.method == "POST":
        form = FichaForm(request.POST, ficha=ficha, exige_consentimento=exige)
        if form.is_valid():
            try:
                criada = ficha is None
                servicos.salvar_ficha(request.user, form.dados(), form.cleaned_data["consentimento"])
            except RegraViolada as erro:
                form.add_error("consentimento", str(erro))
            else:
                messages.success(
                    request,
                    "Ficha salva. Obrigado! Você pode mudar quando quiser." if criada
                    else "Ficha atualizada. Você pode mudar quando quiser.",
                )
                return redirect(proximo or (reverse("ficha:minha") + "?salva=1"))
    else:
        form = FichaForm(ficha=ficha, preselecionar=request.GET.getlist("adicionar"), exige_consentimento=exige)
    salva = request.method == "GET" and request.GET.get("salva") == "1"
    return render(
        request,
        "ficha/formulario.html",
        {
            "form": form,
            "ficha": ficha,
            "exige_consentimento": exige,
            "proximo": proximo,
            "salva": salva,
            "foco_no_titulo": salva,
            "aviso": privacidade.AVISO,
            "nao_e_diagnostico": privacidade.AVISO_NAO_E_DIAGNOSTICO,
            "adicionando": [r for r in request.GET.getlist("adicionar")],
        },
    )


@require_POST
@dono_da_ficha
def dispensar_sugestao(request):
    """"Agora não": a sugestão dessa região não volta por 30 dias."""
    regiao = request.POST.get("regiao", "")
    try:
        servicos.dispensar_sugestao(request.user, regiao)
    except RegraViolada:
        raise Http404
    messages.info(
        request,
        f"Tudo bem. Não vamos sugerir de novo sobre {nome_curto_regiao(regiao)} nos próximos "
        f"{servicos.DIAS_SEM_REPETIR_SUGESTAO} dias. Sua ficha não mudou.",
    )
    return redirect(_destino(request) or "agenda:meus_agendamentos")


@require_POST
@dono_da_ficha
def convite_agora_nao(request):
    """"Agora não" no convite da ficha. Já foi marcado como mostrado; aqui só confirmamos para a pessoa."""
    messages.info(request, "Tudo bem. Você pode preencher a ficha quando quiser, em Minha ficha de saúde, no menu.")
    return redirect("agenda:agendar_dia")


@never_cache
@dono_da_ficha
def apagar_ficha(request):
    ficha = FichaSaude.objects.filter(usuario=request.user).first()
    if ficha is None:
        raise Http404
    if request.method == "POST":
        servicos.apagar_ficha(request.user, apagar_observacoes=bool(request.POST.get("apagar_observacoes")))
        messages.success(request, "Sua ficha de saúde foi apagada. Você pode preencher outra quando quiser.")
        return redirect("ficha:minha")
    return render(request, "ficha/apagar.html", {"ficha": ficha})


@never_cache
@dono_da_ficha
def meus_acessos(request):
    """Quem abriu a minha ficha e quando."""
    acessos = AcessoFicha.objects.filter(colaborador=request.user).exclude(
        finalidade=AcessoFicha.Finalidade.SESMT_AGREGADO
    )[:100]
    return render(request, "ficha/meus_acessos.html", {"acessos": acessos})


def privacidade_da_ficha(request):
    return render(
        request,
        "ficha/privacidade.html",
        {"aviso": privacidade.AVISO, "versao": privacidade.VERSAO_TEXTO, "nao_e_diagnostico": privacidade.AVISO_NAO_E_DIAGNOSTICO},
    )
