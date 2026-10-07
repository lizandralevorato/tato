from datetime import time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import Agendamento, ListaEspera
from apps.agenda.servicos import RegraViolada
from apps.notificacoes.models import Notificacao

from .test_telas import entrar, verificar_acessibilidade


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


@pytest.fixture
def dia_lotado(massoterapeuta, colaborador, segunda, em, cedo):
    """Segunda com só um horário na grade, já ocupado pela Ana."""
    massoterapeuta.disponibilidades.filter(dia_semana=0).delete()
    servicos.adicionar_periodo(massoterapeuta, 0, time(9), time(9, 20))
    return servicos.agendar(colaborador, massoterapeuta, em(segunda, 9), agora=cedo)


def test_cancelamento_avisa_quem_espera(dia_lotado, colaborador, colaborador2, unidade, segunda, cedo):
    entrada = servicos.entrar_na_lista_de_espera(colaborador2, unidade, segunda, agora=cedo)
    servicos.cancelar(dia_lotado, por=colaborador, agora=cedo)
    aviso = Notificacao.objects.get(usuario=colaborador2, tipo=Notificacao.Tipo.VAGA)
    assert "Abriu um horário" in aviso.corpo and "9h" in aviso.corpo
    entrada.refresh_from_db()
    assert entrada.avisado_em is not None and entrada.ativa


def test_reserva_liberada_sem_checkin_tambem_avisa(dia_lotado, colaborador2, unidade, segunda, em):
    servicos.entrar_na_lista_de_espera(colaborador2, unidade, segunda, agora=em(segunda, 7))
    servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 6))
    dia_lotado.refresh_from_db()
    assert dia_lotado.status == Agendamento.Status.EXPIRADO
    assert Notificacao.objects.filter(usuario=colaborador2, tipo=Notificacao.Tipo.VAGA).exists()


def test_quem_agenda_sai_da_lista(dia_lotado, colaborador, colaborador2, unidade, segunda, em, cedo):
    entrada = servicos.entrar_na_lista_de_espera(colaborador2, unidade, segunda, agora=cedo)
    servicos.cancelar(dia_lotado, por=colaborador, agora=cedo)
    servicos.agendar(colaborador2, dia_lotado.massoterapeuta, em(segunda, 9), agora=cedo)
    entrada.refresh_from_db()
    assert not entrada.ativa


def test_espera_por_outro_massoterapeuta_nao_e_avisada(dia_lotado, colaborador, colaborador2, unidade, outro_massoterapeuta, segunda, cedo):
    servicos.entrar_na_lista_de_espera(colaborador2, unidade, segunda, massoterapeuta=outro_massoterapeuta, agora=cedo)
    servicos.cancelar(dia_lotado, por=colaborador, agora=cedo)
    assert not Notificacao.objects.filter(usuario=colaborador2, tipo=Notificacao.Tipo.VAGA).exists()


def test_nao_entra_na_lista_se_ja_tem_massagem_no_dia(dia_lotado, colaborador, unidade, segunda, cedo):
    with pytest.raises(RegraViolada, match="já tem massagem"):
        servicos.entrar_na_lista_de_espera(colaborador, unidade, segunda, agora=cedo)


def test_dia_lotado_aparece_com_lista_de_espera(client, dia_lotado, colaborador2, segunda):
    entrar(client, colaborador2)
    html = client.get(reverse("agenda:agendar_dia")).content.decode()
    assert "Lotado. Entrar na lista de espera" in html

    html = client.get(reverse("agenda:agendar_horario", args=[segunda.isoformat()])).content.decode()
    assert "Me avise se abrir vaga" in html
    verificar_acessibilidade(html)

    resposta = client.post(reverse("agenda:entrar_na_espera"), {"dia": segunda.isoformat()}, follow=True)
    html = resposta.content.decode()
    assert "Você está na lista de espera" in html and "Sair da lista" in html
    verificar_acessibilidade(html)

    entrada = ListaEspera.objects.get(colaborador=colaborador2)
    client.post(reverse("agenda:sair_da_espera", args=[entrada.pk]))
    entrada.refresh_from_db()
    assert not entrada.ativa


def test_lista_de_espera_mostra_quando_abriu_vaga(client, dia_lotado, colaborador, colaborador2, unidade, segunda):
    servicos.entrar_na_lista_de_espera(colaborador2, unidade, segunda)
    servicos.cancelar(dia_lotado, por=colaborador)
    entrar(client, colaborador2)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    assert "Abriu vaga: 1 horário livre" in html
    assert timezone.localdate() <= segunda
