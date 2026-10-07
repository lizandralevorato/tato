from datetime import timedelta

import pytest
from django.urls import reverse

from apps.agenda import servicos
from apps.agenda.models import Agendamento, HistoricoAgendamento, Massoterapeuta, PoliticaBeneficio
from apps.agenda.servicos import RegraViolada
from apps.contas.models import Usuario

from .conftest import SENHA, criar_usuario
from .test_telas import entrar, verificar_acessibilidade

Acao = HistoricoAgendamento.Acao


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


@pytest.fixture
def gestao(unidade):
    return criar_usuario("gestao@teste.local", Usuario.Papel.GESTAO, unidade, "Gestão")


# Regras do encaixe e da exceção


def test_recepcao_agenda_para_alguem_e_fica_no_historico(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo, por=recepcao)
    assert ag.origem == Agendamento.Origem.RECEPCAO
    registro = ag.historico.get()
    assert registro.acao == Acao.AGENDADO_EQUIPE and registro.por == recepcao


def test_encaixe_fora_da_grade(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 8, 20), agora=cedo, por=recepcao, encaixe=True)
    assert ag.origem == Agendamento.Origem.ENCAIXE
    assert ag.historico.get().acao == Acao.ENCAIXE


def test_encaixe_nao_pode_sobrepor_outro_atendimento(massoterapeuta, colaborador, colaborador2, recepcao, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    with pytest.raises(RegraViolada, match="já tem atendimento"):
        servicos.agendar(colaborador2, massoterapeuta, em(segunda, 8, 10), agora=cedo, por=recepcao, encaixe=True)


def test_encaixe_fora_do_expediente(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    with pytest.raises(RegraViolada, match="fora do horário de atendimento"):
        servicos.agendar(colaborador, massoterapeuta, em(segunda, 12), agora=cedo, por=recepcao, encaixe=True)


def test_excecao_permite_passar_do_limite(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    with pytest.raises(RegraViolada, match="Ana já tem massagem neste dia"):
        servicos.agendar(colaborador, massoterapeuta, em(segunda, 13), agora=cedo, por=recepcao)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 13), agora=cedo, por=recepcao, excecao=True)
    assert "Exceção" in ag.historico.get().detalhe


def test_avisa_a_pessoa_quando_a_recepcao_agenda(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo, por=recepcao)
    assert ag.notificacoes.filter(usuario=colaborador).exists()


def test_cada_mudanca_fica_registrada(massoterapeuta, colaborador, recepcao, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8))
    servicos.avisar_chegada(ag, agora=em(segunda, 9, 15))
    servicos.marcar_realizado(ag, agora=em(segunda, 9, 25), por=massoterapeuta.usuario)
    acoes = list(ag.historico.order_by("em").values_list("acao", flat=True))
    assert acoes == [Acao.AGENDADO, Acao.CHECKIN, Acao.CHEGADA, Acao.REALIZADO]


# Telas


def test_fluxo_de_encaixe_pela_tela(client, recepcao, massoterapeuta, colaborador, segunda):
    entrar(client, recepcao)
    busca = client.get(reverse("agenda:recepcao_agendar"), {"q": "ana"})
    assert "ana@teste.local" in busca.content.decode()
    verificar_acessibilidade(busca.content.decode())

    tela = client.get(reverse("agenda:recepcao_agendar"), {"colaborador": colaborador.pk, "dia": segunda.isoformat()})
    html = tela.content.decode()
    assert "Encaixe em outro horário" in html
    verificar_acessibilidade(html)

    resposta = client.post(
        reverse("agenda:recepcao_agendar"),
        {"colaborador": colaborador.pk, "dia": segunda.isoformat(), "horario": "encaixe",
         "m_encaixe": massoterapeuta.pk, "hora_encaixe": "08:20"},
        follow=True,
    )
    assert "Agendado para Ana" in resposta.content.decode()
    ag = Agendamento.objects.get(colaborador=colaborador)
    assert ag.origem == Agendamento.Origem.ENCAIXE


def test_detalhe_do_agendamento_mostra_historico(client, recepcao, massoterapeuta, colaborador, segunda, em):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20))
    servicos.cancelar(ag, por=recepcao)
    entrar(client, recepcao)
    html = client.get(reverse("agenda:recepcao_agendamento", args=[ag.pk])).content.decode()
    assert "Cancelou, por Recepção" in html and "Agendou, por Ana" in html
    verificar_acessibilidade(html)


def test_cadastrar_massoterapeuta_pela_tela(client, recepcao, unidade):
    entrar(client, recepcao)
    assert client.get(reverse("agenda:pessoa_nova")).status_code == 200
    resposta = client.post(
        reverse("agenda:pessoa_nova"),
        {"first_name": "Rita", "last_name": "Melo", "email": "Rita@Teste.local", "papel": "massoterapeuta",
         "unidade": unidade.pk, "is_active": "on", "nova_senha": "uma-senha-boa-123",
         "duracao_sessao_min": 30, "intervalo_min": 10, "atendendo": "on"},
        follow=True,
    )
    assert "Rita Melo cadastrado" in resposta.content.decode()
    rita = Usuario.objects.get(email="rita@teste.local")
    assert rita.check_password("uma-senha-boa-123")
    assert rita.massoterapeuta.duracao_sessao_min == 30


def test_nao_muda_papel_de_quem_ja_atendeu(client, recepcao, massoterapeuta, colaborador, segunda, em, unidade):
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20))
    entrar(client, recepcao)
    resposta = client.post(
        reverse("agenda:pessoa", args=[massoterapeuta.usuario.pk]),
        {"first_name": "Carlos", "email": "carlos@teste.local", "papel": "colaborador", "unidade": unidade.pk,
         "is_active": "on", "duracao_sessao_min": 20, "intervalo_min": 20},
    )
    assert "desmarque Atendendo" in resposta.content.decode()
    assert Massoterapeuta.objects.filter(pk=massoterapeuta.pk).exists()


def test_lista_de_pessoas(client, recepcao, colaborador):
    entrar(client, recepcao)
    html = client.get(reverse("agenda:pessoas"), {"q": "ana"}).content.decode()
    assert "ana@teste.local" in html
    verificar_acessibilidade(html)


def test_editar_regras_do_beneficio(client, recepcao, unidade):
    entrar(client, recepcao)
    html = client.get(reverse("agenda:regras")).content.decode()
    verificar_acessibilidade(html)
    dados = {f: getattr(unidade.politica, f) for f in [
        "max_por_semana", "tolerancia_min", "antecedencia_cancelamento_min", "checkin_abre_min",
        "checkin_prazo_min", "checkin_tolerancia_min", "chegada_abre_min", "dias_para_agendar", "aviso_proximo_min"]}
    dados.update(max_por_semana=3, uma_por_dia="on", falta_conta_no_limite="on")
    client.post(reverse("agenda:regras"), dados)
    assert PoliticaBeneficio.objects.get(unidade=unidade).max_por_semana == 3


def test_colaborador_nao_entra_nas_telas_da_equipe(client, colaborador):
    entrar(client, colaborador)
    for nome in ["agenda:recepcao_agendar", "agenda:pessoas", "agenda:regras", "painel:inicio"]:
        assert client.get(reverse(nome)).status_code == 403


def test_gestao_cai_no_painel(client, gestao):
    assert client.login(email=gestao.email, password=SENHA)
    assert client.get(reverse("inicio")).url == reverse("painel:inicio")
