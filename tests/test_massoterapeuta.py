from datetime import time, timedelta

import pytest
from django.urls import reverse

from apps.agenda import servicos
from apps.agenda.models import Agendamento, Bloqueio, Disponibilidade
from apps.agenda.servicos import ConflitoDeAgenda, RegraViolada

from .test_telas import entrar, verificar_acessibilidade


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


def test_adicionar_periodo_cria_horarios(massoterapeuta, segunda, cedo):
    massoterapeuta.disponibilidades.filter(dia_semana=0).delete()
    servicos.adicionar_periodo(massoterapeuta, 0, time(9), time(10))
    rotulos = [servicos.formatar_hora(h.inicio) for h in servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, cedo)]
    assert rotulos == ["9h", "9h40"]


def test_periodo_nao_pode_sobrepor_outro(massoterapeuta):
    with pytest.raises(RegraViolada, match="se sobrepõe"):
        servicos.adicionar_periodo(massoterapeuta, 0, time(11), time(14))


def test_periodo_precisa_caber_uma_sessao(massoterapeuta):
    with pytest.raises(RegraViolada, match="pelo menos 20 minutos"):
        servicos.adicionar_periodo(massoterapeuta, 0, time(12), time(12, 10))


def test_remover_periodo_mantem_ou_cancela_agendamentos(massoterapeuta, colaborador, colaborador2, segunda, em, cedo):
    manha = massoterapeuta.disponibilidades.get(dia_semana=0, hora_inicio=time(8))
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    assert servicos.agendamentos_no_periodo(manha, cedo) == [ag]

    servicos.remover_periodo(manha, por=massoterapeuta.usuario, cancelar_agendamentos=True, agora=cedo)
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.CANCELADO
    assert ag.cancelado_por == massoterapeuta.usuario
    assert not Disponibilidade.objects.filter(pk=manha.pk).exists()


def test_folga_com_gente_marcada_pede_confirmacao(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    inicio, fim = em(segunda, 0), em(segunda + timedelta(days=1), 0)
    with pytest.raises(ConflitoDeAgenda) as erro:
        servicos.marcar_ausencia(massoterapeuta, inicio, fim, Bloqueio.Motivo.FOLGA, por=massoterapeuta.usuario, agora=cedo)
    assert erro.value.agendamentos == [ag]
    assert not massoterapeuta.bloqueios.exists()

    servicos.marcar_ausencia(
        massoterapeuta, inicio, fim, Bloqueio.Motivo.FOLGA, por=massoterapeuta.usuario, cancelar_agendamentos=True, agora=cedo
    )
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.CANCELADO
    assert servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, cedo) == []
    aviso = ag.notificacoes.get(usuario=colaborador)
    assert "Carlos não vai poder atender" in aviso.corpo


def test_tela_meus_horarios_adiciona_e_remove(client, massoterapeuta):
    entrar(client, massoterapeuta.usuario)
    massoterapeuta.disponibilidades.filter(dia_semana=5).delete()
    resposta = client.post(
        reverse("agenda:disponibilidade"),
        {"adicionar_periodo": "1", "periodo-dia_semana": 5, "periodo-hora_inicio": "09:00", "periodo-hora_fim": "12:00"},
        follow=True,
    )
    html = resposta.content.decode()
    assert "Horário adicionado: Sábado" in html
    verificar_acessibilidade(html)

    periodo = massoterapeuta.disponibilidades.get(dia_semana=5)
    confirmacao = client.get(reverse("agenda:remover_periodo", args=[periodo.pk]))
    verificar_acessibilidade(confirmacao.content.decode())
    client.post(reverse("agenda:remover_periodo", args=[periodo.pk]))
    assert not massoterapeuta.disponibilidades.filter(dia_semana=5).exists()


def test_tela_marcar_folga_com_conflito(client, massoterapeuta, colaborador, segunda, em):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20))
    entrar(client, massoterapeuta.usuario)
    dados = {"marcar_ausencia": "1", "ausencia-motivo": "folga", "ausencia-data_inicio": segunda.isoformat()}
    html = client.post(reverse("agenda:disponibilidade"), dados).content.decode()
    assert "Há pessoas marcadas nesse período" in html and "com Ana" in html
    verificar_acessibilidade(html)

    dados["ausencia-cancelar_agendamentos"] = "on"
    resposta = client.post(reverse("agenda:disponibilidade"), dados, follow=True)
    assert "Folga registrada" in resposta.content.decode()
    assert massoterapeuta.bloqueios.filter(motivo="folga").exists()


def test_massoterapeuta_so_remove_os_proprios_horarios(client, massoterapeuta, outro_massoterapeuta):
    entrar(client, massoterapeuta.usuario)
    periodo = outro_massoterapeuta.disponibilidades.first()
    assert client.get(reverse("agenda:remover_periodo", args=[periodo.pk])).status_code == 404
