from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.agenda.views import acesso
from apps.contas.models import Usuario
from apps.notificacoes import avisos

from .forms import ComunicadoForm
from .models import Comunicado, LeituraComunicado


@login_required
def lista(request):
    comunicados = list(Comunicado.objects.para(request.user).select_related("unidade", "autor")[:50])
    lidos = set(
        LeituraComunicado.objects.filter(usuario=request.user, comunicado__in=comunicados).values_list(
            "comunicado_id", flat=True
        )
    )
    novos = [c for c in comunicados if c.pk not in lidos]
    LeituraComunicado.objects.bulk_create(
        [LeituraComunicado(comunicado=c, usuario=request.user) for c in novos], ignore_conflicts=True
    )
    return render(
        request,
        "comunicados/lista.html",
        {"itens": [{"c": c, "novo": c.pk not in lidos} for c in comunicados], "total_novos": len(novos)},
    )


def _destinatarios(comunicado):
    pessoas = Usuario.objects.filter(is_active=True, inscricoes_push__isnull=False).distinct()
    if comunicado.unidade_id:
        pessoas = pessoas.filter(Q(unidade_id=comunicado.unidade_id) | Q(unidade__isnull=True))
    if comunicado.publico == Comunicado.Publico.MASSOTERAPEUTAS:
        pessoas = pessoas.filter(papel=Usuario.Papel.MASSOTERAPEUTA)
    return pessoas


@acesso.equipe
def gerenciar(request):
    comunicados = Comunicado.objects.select_related("unidade", "autor")
    if request.user.unidade_id:
        comunicados = comunicados.filter(Q(unidade__isnull=True) | Q(unidade_id=request.user.unidade_id))
    return render(request, "comunicados/gerenciar.html", {"comunicados": comunicados})


@acesso.equipe
def editar(request, pk=None):
    comunicado = get_object_or_404(Comunicado, pk=pk) if pk else None
    form = ComunicadoForm(request.POST or None, instance=comunicado)
    if not comunicado and request.method == "GET":
        form.initial["unidade"] = request.user.unidade_id
    if request.method == "POST" and form.is_valid():
        comunicado = form.save(commit=False)
        if comunicado.autor_id is None:
            comunicado.autor = request.user
        comunicado.save()
        texto = "Comunicado publicado." if comunicado.ativo else "Comunicado salvo, mas não publicado."
        if form.cleaned_data["avisar"] and comunicado.ativo:
            enviados = len(avisos.comunicado(comunicado, _destinatarios(comunicado)))
            texto += f" Aviso enviado para {enviados} pessoa{'s' if enviados != 1 else ''} com notificações ativas."
        messages.success(request, texto)
        return redirect("comunicados:gerenciar")
    return render(request, "comunicados/editar.html", {"form": form, "comunicado": comunicado})


@acesso.equipe
def excluir(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if request.method == "POST":
        comunicado.delete()
        messages.success(request, f"Comunicado excluído: {comunicado.titulo}.")
        return redirect("comunicados:gerenciar")
    return render(request, "comunicados/excluir.html", {"comunicado": comunicado})
