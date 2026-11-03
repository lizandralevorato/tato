"""Permissões da ficha, sempre verificadas no servidor.

Diferente de `agenda.views.acesso`, aqui o superusuário NÃO passa por cima do papel:
a ficha é dado pessoal e só quem tem o papel certo a vê.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from apps.contas.models import Usuario

Papel = Usuario.Papel


def _papel_estrito(*papeis):
    def decorador(view):
        @login_required
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if request.user.papel not in papeis:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return envolvida

    return decorador


# Quem agenda massagem tem ficha. Cada pessoa mexe só na própria.
dono_da_ficha = _papel_estrito(Papel.COLABORADOR, Papel.ADMINISTRADOR, Papel.SESMT)
# O massoterapeuta abre a ficha de um atendimento dele, dentro da janela.
massoterapeuta = _papel_estrito(Papel.MASSOTERAPEUTA)
# Só o SESMT vê fichas de outras pessoas, o painel de saúde e o registro de acessos.
sesmt = _papel_estrito(Papel.SESMT)
