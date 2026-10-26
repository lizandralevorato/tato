from datetime import timedelta

import pytest
from django.urls import reverse

from apps.agenda import servicos
from apps.contas.models import PerfilAcessibilidade
from apps.notificacoes import tarefas
from apps.notificacoes.models import Notificacao

from .test_telas import entrar

# Massagem às 10h: check-in abre às 8h, prazo 9h, limite 9h05.
ESCOLHAS = [15, 30, 45, 60, 120, 180]


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


def escolher(usuario, minutos):
    PerfilAcessibilidade.objects.update_or_create(usuario=usuario, defaults={"lembrete_checkin_min": minutos})


def lembretes(usuario):
    return Notificacao.objects.filter(usuario=usuario, tipo=Notificacao.Tipo.LEMBRETE)


def test_opcoes_disponiveis_e_padrao():
    assert [minutos for minutos, _ in PerfilAcessibilidade.LEMBRETES_CHECKIN] == ESCOLHAS
    assert PerfilAcessibilidade._meta.get_field("lembrete_checkin_min").default == 60


@pytest.mark.parametrize("minutos", ESCOLHAS)
def test_lembrete_sai_no_tempo_escolhido(massoterapeuta, colaborador, segunda, em, cedo, minutos):
    escolher(colaborador, minutos)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    prazo = em(segunda, 9)
    assert tarefas.enviar_lembretes(agora=prazo - timedelta(minutes=minutos + 1)) == 0
    assert tarefas.enviar_lembretes(agora=prazo - timedelta(minutes=minutos - 1)) == 1
    assert lembretes(colaborador).count() == 1


def test_lembrete_nao_repete_nos_ciclos_seguintes(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 45)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 20)) == 1
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 21)) == 0
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 50)) == 0


def test_cada_pessoa_recebe_no_seu_tempo(massoterapeuta, colaborador, colaborador2, segunda, em, cedo):
    outro = colaborador2
    escolher(colaborador, 15)
    escolher(outro, 120)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    servicos.agendar(outro, massoterapeuta, em(segunda, 10, 40), agora=cedo)

    tarefas.enviar_lembretes(agora=em(segunda, 8, 30))  # Bruno (prazo 9h40, 2 h antes = 7h40) já recebeu
    assert lembretes(outro).count() == 1
    assert lembretes(colaborador).count() == 0

    tarefas.enviar_lembretes(agora=em(segunda, 8, 50))  # Ana (prazo 9h, 15 min antes = 8h45)
    assert lembretes(colaborador).count() == 1


def test_lembrete_nao_sai_depois_do_prazo(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 30)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 9, 1)) == 0
    assert lembretes(colaborador).count() == 0


def test_lembrete_com_checkin_aberto_pede_para_fazer_checkin(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 30)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    tarefas.enviar_lembretes(agora=em(segunda, 8, 31))
    notificacao = lembretes(colaborador).get()
    assert notificacao.titulo == "Faça o check-in da massagem"
    assert "Faça o check-in até 9h." in notificacao.corpo
    assert "Sem check-in até 9h05" in notificacao.corpo


def test_lembrete_antes_de_abrir_informa_a_abertura(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 180)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    tarefas.enviar_lembretes(agora=em(segunda, 6, 30))
    notificacao = lembretes(colaborador).get()
    assert notificacao.titulo == "Lembrete da sua massagem"
    assert "O check-in abre às 8h e vai até 9h." in notificacao.corpo


def test_quem_fez_checkin_nao_recebe_lembrete(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 30)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8, 10))
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 40)) == 0


def test_ultimo_aviso_continua_depois_do_lembrete(massoterapeuta, colaborador, segunda, em, cedo):
    escolher(colaborador, 30)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 31)) == 1
    assert tarefas.avisar_prazo_checkin(agora=em(segunda, 9, 1)) == 1
    tipos = set(Notificacao.objects.filter(usuario=colaborador).values_list("tipo", flat=True))
    assert tipos == {Notificacao.Tipo.LEMBRETE, Notificacao.Tipo.ULTIMO_AVISO}


def test_checkin_desligado_ignora_a_preferencia(massoterapeuta, colaborador, segunda, em, cedo):
    politica = servicos.politica_da(massoterapeuta.unidade)
    politica.checkin_prazo_min = 0
    politica.save()
    escolher(colaborador, 180)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 7)) == 0


def test_preferencia_aparece_e_salva_na_tela(client, colaborador):
    entrar(client, colaborador)
    html = client.get(reverse("contas:preferencias")).content.decode()
    for _, texto in PerfilAcessibilidade.LEMBRETES_CHECKIN:
        assert texto in html

    client.post(
        reverse("contas:preferencias"),
        {"tamanho_texto": 100, "fonte": "padrao", "tema": "sistema", "fala_velocidade": 100, "lembrete_checkin_min": 180},
    )
    assert PerfilAcessibilidade.objects.get(usuario=colaborador).lembrete_checkin_min == 180


def test_tempo_fora_das_opcoes_e_recusado(client, colaborador):
    entrar(client, colaborador)
    client.post(
        reverse("contas:preferencias"),
        {"tamanho_texto": 100, "fonte": "padrao", "tema": "sistema", "fala_velocidade": 100, "lembrete_checkin_min": 7},
    )
    assert PerfilAcessibilidade.objects.get(usuario=colaborador).lembrete_checkin_min == 60
