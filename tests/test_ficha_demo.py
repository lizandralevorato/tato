"""Etapa (g): demonstração, páginas públicas e documentação da ficha de saúde."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Agendamento
from apps.contas.models import Usuario
from apps.ficha import servicos
from apps.ficha.models import FichaSaude

from .test_telas import verificar_acessibilidade


def popular(**opcoes):
    saida = StringIO()
    call_command("popular_demo", stdout=saida, **opcoes)
    return saida.getvalue()


def test_demo_cria_fichas_e_um_caso_de_regiao_recorrente(db):
    popular()
    ana = Usuario.objects.get(email="ana@demo.local")
    bruno = Usuario.objects.get(email="bruno@demo.local")
    carla = Usuario.objects.get(email="carla@demo.local")
    assert FichaSaude.objects.filter(usuario=ana).exists() and FichaSaude.objects.filter(usuario=bruno).exists()
    assert not FichaSaude.objects.filter(usuario=carla).exists()
    assert "anticoagulante" in FichaSaude.objects.get(usuario=ana).condicoes
    [rec] = [r for r in servicos.recorrencias(ana) if r.regiao == "ombros"]
    assert rec.vezes >= 3 and not rec.apenas_texto
    assert servicos.sugestoes_para(carla) == []


def test_demo_pode_rodar_duas_vezes_sem_duplicar(db):
    popular()
    fichas, agendamentos = FichaSaude.objects.count(), Agendamento.objects.count()
    versoes = sum(f.versoes.count() for f in FichaSaude.objects.all())
    popular()
    assert FichaSaude.objects.count() == fichas
    assert sum(f.versoes.count() for f in FichaSaude.objects.all()) == versoes
    # Os pedidos antigos de demonstração não se repetem (os de hoje podem ser recriados pelas regras normais).
    assert Agendamento.objects.filter(status=Agendamento.Status.REALIZADO).count() == 3
    assert Agendamento.objects.count() >= agendamentos


def test_demo_agora_cria_atendimento_para_testar_ver_ficha(db):
    saida = popular(agora=True)
    inicio = timezone.now() + timedelta(minutes=30)
    if timezone.localtime(inicio).date() != timezone.localdate():
        pytest.skip("perto da meia-noite o atendimento cairia amanhã")
    ag = Agendamento.objects.get(colaborador__email="ana@demo.local", massoterapeuta__usuario__email="carlos@demo.local", foco_regioes=["ombros"], status="confirmado")
    assert servicos.na_janela_de_acesso(ag)
    assert "Atendimento de teste" in saida


def test_como_funciona_explica_a_ficha_e_que_e_opcional(client, db):
    html = client.get(reverse("como_funciona")).content.decode()
    assert "Ficha de saúde e pedido para cada massagem (opcional)" in html
    assert "você agenda do mesmo jeito sem ela" in html
    assert "O administrador do site não vê a ficha" in html
    assert reverse("ficha:privacidade") in html
    verificar_acessibilidade(html)


def test_declaracao_de_acessibilidade_cita_a_ficha(client, db):
    html = client.get(reverse("acessibilidade")).content.decode()
    assert "Ficha de saúde em 3 etapas" in html and "Ouvir ficha" in html
    verificar_acessibilidade(html)


def test_rodape_leva_ao_aviso_de_privacidade(client, db):
    assert reverse("ficha:privacidade") in client.get(reverse("como_funciona")).content.decode()
