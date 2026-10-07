from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from apps.contas.models import Usuario

from ..servicos import RegraViolada

Papel = Usuario.Papel


def papel_requerido(*papeis):
    def decorador(view):
        @login_required
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if request.user.papel not in papeis and not request.user.is_superuser:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return envolvida

    return decorador


colaborador = papel_requerido(Papel.COLABORADOR, Papel.RECEPCAO, Papel.GESTAO)
massoterapeuta = papel_requerido(Papel.MASSOTERAPEUTA)
equipe = papel_requerido(Papel.RECEPCAO, Papel.GESTAO)


def executar(request, acao, sucesso, destino, *args, **kwargs):
    """Roda uma regra de negócio e mostra sucesso ou o motivo da recusa."""
    from django.contrib import messages

    try:
        resultado = acao(*args, **kwargs)
    except RegraViolada as erro:
        messages.error(request, str(erro))
    else:
        messages.success(request, sucesso(resultado) if callable(sucesso) else sucesso)
    return redirect(destino)
