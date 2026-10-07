from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.agenda import servicos
from apps.agenda.models import Agendamento, Bloqueio, Massoterapeuta
from apps.agenda.servicos import RegraViolada
from apps.contas.models import Usuario


@pytest.fixture
def cedo(segunda, em):
    """"Agora" = domingo à noite, antes da semana de testes."""
    return em(segunda, 7) - timedelta(hours=12)


def test_horarios_do_dia_respeitam_duracao_e_intervalo(massoterapeuta, segunda, cedo):
    horarios = servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, agora=cedo)
    rotulos = [servicos.formatar_hora(h.inicio) for h in horarios]
    assert rotulos == ["8h", "8h40", "9h20", "10h", "10h40", "11h20", "13h", "13h40", "14h20", "15h", "15h40", "16h20"]


def test_bloqueio_remove_horarios_sobrepostos(massoterapeuta, segunda, em, cedo):
    Bloqueio.objects.create(massoterapeuta=massoterapeuta, inicio=em(segunda, 8, 30), fim=em(segunda, 9, 30))
    inicios = {h.inicio for h in servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, agora=cedo)}
    assert em(segunda, 8, 40) not in inicios
    assert em(segunda, 9, 20) not in inicios
    assert em(segunda, 8) in inicios


def test_horario_passado_nao_aparece(massoterapeuta, segunda, em):
    horarios = servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, agora=em(segunda, 12))
    assert all(h.inicio > em(segunda, 12) for h in horarios)


def test_agendar_ocupa_o_horario(massoterapeuta, colaborador, colaborador2, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with pytest.raises(RegraViolada, match="não está mais livre"):
        servicos.agendar(colaborador2, massoterapeuta, em(segunda, 9, 20), agora=cedo)


def test_banco_impede_dois_agendamentos_no_mesmo_horario(massoterapeuta, colaborador, colaborador2, segunda, em):
    inicio = em(segunda, 9, 20)
    Agendamento.objects.create(colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20))
    with pytest.raises(IntegrityError):
        Agendamento.objects.create(colaborador=colaborador2, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20))


def test_horario_cancelado_volta_a_ficar_livre(massoterapeuta, colaborador, colaborador2, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.cancelar(ag, por=recepcao, agora=cedo)
    servicos.agendar(colaborador2, massoterapeuta, em(segunda, 9, 20), agora=cedo)


def test_uma_massagem_por_dia(massoterapeuta, outro_massoterapeuta, colaborador, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    with pytest.raises(RegraViolada, match="já tem massagem neste dia"):
        servicos.agendar(colaborador, outro_massoterapeuta, em(segunda, 13), agora=cedo)


def test_limite_de_duas_por_semana(massoterapeuta, colaborador, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=1), 8), agora=cedo)
    with pytest.raises(RegraViolada, match="já usou as 2 massagens"):
        servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=2), 8), agora=cedo)
    # Na semana seguinte o limite recomeça.
    servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=7), 8), agora=cedo)


def test_falta_conta_no_limite_e_cancelamento_nao(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    primeira = servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    segunda_vez = servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=1), 8), agora=cedo)
    servicos.marcar_falta(primeira, agora=em(segunda, 8, 6))
    servicos.cancelar(segunda_vez, por=recepcao, agora=cedo)
    assert servicos.uso_na_semana(colaborador, segunda, servicos.politica_da(massoterapeuta.unidade)) == 1


def test_colaborador_so_cancela_ate_15_minutos_antes(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with pytest.raises(RegraViolada, match="até 15 minutos antes"):
        servicos.cancelar(ag, por=colaborador, agora=em(segunda, 9, 10))
    servicos.cancelar(ag, por=colaborador, agora=em(segunda, 9, 5))
    assert ag.status == Agendamento.Status.CANCELADO


def test_recepcao_cancela_a_qualquer_momento(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.cancelar(ag, por=recepcao, agora=em(segunda, 9, 19))
    assert ag.cancelado_por == recepcao


# Check-in (confirmar que vai): prazo 1 h antes, tolerância 5 min
def test_janela_do_checkin(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    assert ag.status == Agendamento.Status.AGENDADO
    assert servicos.janela_checkin(ag) == (em(segunda, 7, 20), em(segunda, 8, 20), em(segunda, 8, 25))


def test_checkin_so_depois_de_abrir(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with pytest.raises(RegraViolada, match="abre às 7h20"):
        servicos.fazer_checkin(ag, agora=em(segunda, 7))
    servicos.fazer_checkin(ag, agora=em(segunda, 7, 30))
    assert ag.status == Agendamento.Status.CONFIRMADO
    with pytest.raises(RegraViolada, match="já foi feito"):
        servicos.fazer_checkin(ag, agora=em(segunda, 7, 31))


def test_checkin_na_tolerancia_ainda_vale(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8, 25))
    assert ag.status == Agendamento.Status.CONFIRMADO


def test_checkin_depois_da_tolerancia_e_recusado(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with pytest.raises(RegraViolada, match="terminou às 8h25"):
        servicos.fazer_checkin(ag, agora=em(segunda, 8, 26))


def test_sem_checkin_a_reserva_e_liberada_5_minutos_apos_o_prazo(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 24)) == []
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 25)) == []  # ainda na tolerância
    liberadas = servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 25, 1))
    assert [a.pk for a in liberadas] == [ag.pk]
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.EXPIRADO


def test_reserva_liberada_fica_disponivel_para_outra_pessoa(
    massoterapeuta, colaborador, colaborador2, segunda, em, cedo
):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    depois = em(segunda, 8, 26)
    livres = {h.inicio for h in servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, agora=depois)}
    assert em(segunda, 9, 20) not in livres

    servicos.liberar_reservas_sem_checkin(agora=depois)
    livres = {h.inicio for h in servicos.horarios_do_massoterapeuta(massoterapeuta, segunda, agora=depois)}
    assert em(segunda, 9, 20) in livres
    novo = servicos.agendar(colaborador2, massoterapeuta, em(segunda, 9, 20), agora=depois)
    # Agendou já dentro da janela do check-in: fica confirmado na hora e não será liberado.
    assert novo.status == Agendamento.Status.CONFIRMADO
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 40)) == []


def test_reserva_liberada_nao_conta_no_limite_semanal(massoterapeuta, colaborador, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 26))
    politica = servicos.politica_da(massoterapeuta.unidade)
    assert servicos.uso_na_semana(colaborador, segunda, politica) == 0


def test_quem_fez_checkin_nao_perde_a_reserva(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8))
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 9)) == []


def test_checkin_depois_da_liberacao_explica_o_que_houve(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    copia_antiga = Agendamento.objects.get(pk=ag.pk)  # tela aberta antes da liberação
    servicos.liberar_reservas_sem_checkin(agora=em(segunda, 8, 26))
    with pytest.raises(RegraViolada, match="acabou de ser liberada"):
        servicos.fazer_checkin(copia_antiga, agora=em(segunda, 8, 25))
    ag.refresh_from_db()
    with pytest.raises(RegraViolada, match="reserva foi liberada"):
        servicos.fazer_checkin(ag, agora=em(segunda, 8, 27))


def test_checkin_desligado_na_politica_nao_libera(massoterapeuta, colaborador, segunda, em, cedo):
    politica = servicos.politica_da(massoterapeuta.unidade)
    politica.checkin_prazo_min = 0
    politica.save()
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 9, 10)) == []


def test_agendar_em_cima_da_hora_ja_faz_checkin(massoterapeuta, colaborador, segunda, em):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=em(segunda, 8, 50))
    assert ag.status == Agendamento.Status.CONFIRMADO
    assert ag.confirmado_em == em(segunda, 8, 50)


# Chegada na sala ("Cheguei")
def test_chegada_so_na_janela(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8))
    with pytest.raises(RegraViolada, match="abre às 9h10"):
        servicos.avisar_chegada(ag, agora=em(segunda, 9))
    servicos.avisar_chegada(ag, agora=em(segunda, 9, 15))
    assert ag.status == Agendamento.Status.CHEGOU


def test_chegada_depois_da_tolerancia_e_recusada(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8))
    with pytest.raises(RegraViolada, match="tolerância"):
        servicos.avisar_chegada(ag, agora=em(segunda, 9, 26))


def test_falta_so_depois_da_tolerancia(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with pytest.raises(RegraViolada, match="a partir de 9h25"):
        servicos.marcar_falta(ag, agora=em(segunda, 9, 22))
    servicos.marcar_falta(ag, agora=em(segunda, 9, 25))
    assert ag.status == Agendamento.Status.FALTA


def test_sem_preferencia_escolhe_quem_tem_menos_atendimentos(
    massoterapeuta, outro_massoterapeuta, colaborador, colaborador2, segunda, em, cedo
):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    escolhido = servicos.escolher_massoterapeuta(massoterapeuta.unidade, em(segunda, 9, 20), agora=cedo)
    assert escolhido == outro_massoterapeuta


def test_pausa_bloqueia_novos_e_avisa_conflitos(massoterapeuta, colaborador, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    conflitos = servicos.pausar(massoterapeuta, 15, agora=em(segunda, 9, 10))
    assert [c.inicio for c in conflitos] == [em(segunda, 9, 20)]


def test_formatacao_natural_das_horas(segunda, em):
    assert servicos.formatar_hora(em(segunda, 9, 5)) == "9h05"
    assert servicos.formatar_hora(em(segunda, 13)) == "13h"


def test_dia_com_massagem_ja_iniciada_aparece_como_ocupado(massoterapeuta, colaborador, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    dias = servicos.dias_para_agendar(massoterapeuta.unidade, colaborador, agora=em(segunda, 8, 10))
    assert dias[0]["dia"] == segunda and dias[0]["ja_tem_agendamento"]


def test_horario_que_ja_passou_nao_e_liberado(massoterapeuta, colaborador, segunda, em, cedo):
    """Liberar só serve se outra pessoa ainda pode usar; senão, fica para marcar falta."""
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    assert servicos.liberar_reservas_sem_checkin(agora=em(segunda, 9, 30)) == []
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.AGENDADO


# Papéis: quem atende não agenda, quem agenda não atende
def test_massoterapeuta_nao_agenda_massagem(massoterapeuta, outro_massoterapeuta, segunda, em, cedo):
    with pytest.raises(RegraViolada, match="Massoterapeutas não podem agendar"):
        servicos.agendar(outro_massoterapeuta.usuario, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    assert not Agendamento.objects.exists()


def test_admin_nao_aceita_massoterapeuta_como_colaborador(massoterapeuta, outro_massoterapeuta, segunda, em):
    inicio = em(segunda, 9, 20)
    ag = Agendamento(colaborador=outro_massoterapeuta.usuario, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20))
    with pytest.raises(ValidationError) as erro:
        ag.full_clean()
    assert "colaborador" in erro.value.message_dict


def test_colaborador_nao_vira_massoterapeuta_sem_mudar_o_papel(colaborador, unidade):
    m = Massoterapeuta(usuario=colaborador, unidade=unidade)
    with pytest.raises(ValidationError) as erro:
        m.full_clean()
    assert "usuario" in erro.value.message_dict


def test_massoterapeuta_nao_muda_para_colaborador_com_cadastro_ativo(massoterapeuta):
    usuario = massoterapeuta.usuario
    usuario.papel = Usuario.Papel.COLABORADOR
    with pytest.raises(ValidationError) as erro:
        usuario.full_clean()
    assert "papel" in erro.value.message_dict
