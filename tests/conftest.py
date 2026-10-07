from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.agenda.models import Disponibilidade, Massoterapeuta, PoliticaBeneficio, Unidade
from apps.contas.models import PerfilAcessibilidade, Usuario

SENHA = "senha-de-teste-123"


@pytest.fixture
def unidade(db):
    unidade = Unidade.objects.create(nome="Londrina")
    PoliticaBeneficio.objects.create(unidade=unidade)
    return unidade


def criar_usuario(email, papel, unidade, nome="Pessoa"):
    usuario = Usuario.objects.create_user(email=email, password=SENHA, first_name=nome, papel=papel, unidade=unidade)
    PerfilAcessibilidade.objects.filter(usuario=usuario).update(configurado=True)
    return usuario


def criar_massoterapeuta(unidade, email, nome):
    usuario = criar_usuario(email, Usuario.Papel.MASSOTERAPEUTA, unidade, nome)
    m = Massoterapeuta.objects.create(usuario=usuario, unidade=unidade, duracao_sessao_min=20, intervalo_min=20)
    for dia in range(7):
        Disponibilidade.objects.create(massoterapeuta=m, dia_semana=dia, hora_inicio=time(8), hora_fim=time(11, 40))
        Disponibilidade.objects.create(massoterapeuta=m, dia_semana=dia, hora_inicio=time(13), hora_fim=time(16, 40))
    return m


@pytest.fixture
def massoterapeuta(unidade):
    return criar_massoterapeuta(unidade, "carlos@teste.local", "Carlos")


@pytest.fixture
def outro_massoterapeuta(unidade):
    return criar_massoterapeuta(unidade, "lucia@teste.local", "Lúcia")


@pytest.fixture
def colaborador(unidade):
    return criar_usuario("ana@teste.local", Usuario.Papel.COLABORADOR, unidade, "Ana")


@pytest.fixture
def colaborador2(unidade):
    return criar_usuario("bruno@teste.local", Usuario.Papel.COLABORADOR, unidade, "Bruno")


@pytest.fixture
def recepcao(unidade):
    return criar_usuario("recepcao@teste.local", Usuario.Papel.RECEPCAO, unidade, "Recepção")


@pytest.fixture
def segunda():
    """Uma segunda-feira futura, para os testes não dependerem do dia de hoje."""
    hoje = timezone.localdate()
    return hoje + timedelta(days=7 - hoje.weekday())


@pytest.fixture
def em():
    """em(dia, 9, 20) -> datetime com fuso de São Paulo."""
    def _em(dia, hora, minuto=0, segundo=0):
        return timezone.make_aware(datetime.combine(dia, time(hora, minuto, segundo)))
    return _em
