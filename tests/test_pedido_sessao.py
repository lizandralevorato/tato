"""Etapa (c): foco e observação opcionais em cada agendamento."""

from datetime import timedelta

import pytest
from django.urls import reverse

from apps.agenda import servicos
from apps.agenda.models import Agendamento, HistoricoAgendamento
from apps.agenda.servicos import RegraViolada

from .test_telas import entrar, verificar_acessibilidade

CONFIRMAR = "agenda:agendar_confirmar"


@pytest.fixture
def amanha(em):
    from django.utils import timezone

    return em(timezone.localdate() + timedelta(days=1), 8)


# Regras


def test_agendar_com_pedido_grava_foco_na_ordem_do_vocabulario_sem_repetir(colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(
        colaborador, massoterapeuta, amanha, foco_regioes=["lombar", "ombros", "ombros"], observacao="  hoje ombros  "
    )
    ag.refresh_from_db()
    assert ag.foco_regioes == ["ombros", "lombar"]
    assert ag.observacao == "hoje ombros" and ag.observacao_em


def test_agendar_sem_pedido_continua_igual(colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    assert ag.foco_regioes == [] and ag.observacao == "" and ag.observacao_em is None


def test_pedido_invalido_nao_cria_agendamento(colaborador, massoterapeuta, amanha):
    with pytest.raises(RegraViolada):
        servicos.agendar(colaborador, massoterapeuta, amanha, foco_regioes=["coracao"])
    with pytest.raises(RegraViolada, match="300"):
        servicos.agendar(colaborador, massoterapeuta, amanha, observacao="x" * 301)
    assert not Agendamento.objects.exists()


def test_observacao_editavel_so_ate_o_checkin_abrir(colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    abre = servicos.editavel_ate(ag)
    assert abre == amanha - timedelta(minutes=120)
    assert servicos.pode_editar_observacao(ag, abre - timedelta(minutes=1))
    assert not servicos.pode_editar_observacao(ag, abre)
    servicos.atualizar_pedido(ag, ["pescoco"], "ok", colaborador, abre - timedelta(minutes=1))
    with pytest.raises(RegraViolada, match="check-in abrir"):
        servicos.atualizar_pedido(ag, ["pescoco"], "tarde", colaborador, abre + timedelta(minutes=1))
    ag.refresh_from_db()
    assert ag.observacao == "ok"


def test_so_quem_agendou_edita_e_so_agendamento_pendente(colaborador, colaborador2, massoterapeuta, amanha, administrador):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    with pytest.raises(RegraViolada):
        servicos.atualizar_pedido(ag, [], "x", colaborador2)
    with pytest.raises(RegraViolada):
        servicos.atualizar_pedido(ag, [], "x", administrador)
    servicos.cancelar(ag, colaborador)
    assert not servicos.pode_editar_observacao(ag)


def test_mudar_o_pedido_fica_no_historico_sem_o_texto(colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    servicos.atualizar_pedido(ag, ["ombros"], "texto reservado", colaborador)
    evento = ag.historico.get(acao=HistoricoAgendamento.Acao.PEDIDO)
    assert evento.por == colaborador and "reservado" not in evento.detalhe


def test_cancelar_mantem_a_observacao_no_historico(colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha, foco_regioes=["ombros"], observacao="ombros")
    servicos.cancelar(ag, colaborador)
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.CANCELADO
    assert ag.foco_regioes == ["ombros"] and ag.observacao == "ombros"


# Tela do passo 3


def test_passo_3_tem_o_bloco_opcional_antes_do_botao_confirmar(client, colaborador, massoterapeuta, amanha):
    entrar(client, colaborador)
    resposta = client.get(reverse(CONFIRMAR), {"inicio": amanha.isoformat(), "m": massoterapeuta.pk})
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Quer contar algo para esta sessão?" in html
    assert "Onde você quer focar hoje?" in html
    assert "Ex.: já fiz massagem esta semana, hoje quero focar nos ombros." in html
    assert 'maxlength="300"' in html and 'id="observacao-contador"' in html
    assert html.index("Quer contar algo para esta sessão?") < html.index("Confirmar agendamento")
    assert "<fieldset" in html and "<legend>Onde você quer focar hoje?</legend>" in html
    verificar_acessibilidade(html)


def test_reserva_sem_pedido_funciona_exatamente_como_antes(client, colaborador, massoterapeuta, amanha):
    entrar(client, colaborador)
    resposta = client.post(reverse(CONFIRMAR), {"inicio": amanha.isoformat(), "m": massoterapeuta.pk}, follow=True)
    assert "Massagem agendada" in resposta.content.decode()
    ag = Agendamento.objects.get()
    assert ag.foco_regioes == [] and ag.observacao == ""


def test_reservar_com_foco_e_observacao(client, colaborador, massoterapeuta, amanha):
    entrar(client, colaborador)
    client.post(
        reverse(CONFIRMAR),
        {"inicio": amanha.isoformat(), "m": massoterapeuta.pk, "foco_regioes": ["ombros", "pescoco"], "observacao": "já fiz massagem"},
    )
    ag = Agendamento.objects.get()
    assert ag.foco_regioes == ["pescoco", "ombros"] and ag.observacao == "já fiz massagem"
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    assert "foco em pescoço e ombros" in html and "já fiz massagem" in html
    assert reverse("agenda:pedido", args=[ag.pk]) in html


def test_observacao_longa_demais_volta_com_erro_e_nao_reserva(client, colaborador, massoterapeuta, amanha):
    entrar(client, colaborador)
    resposta = client.post(
        reverse(CONFIRMAR), {"inicio": amanha.isoformat(), "m": massoterapeuta.pk, "observacao": "x" * 301}
    )
    html = resposta.content.decode()
    assert resposta.status_code == 200 and not Agendamento.objects.exists()
    assert 'aria-invalid="true"' in html and "observacao-erro" in html and "resumo-erros" in html
    verificar_acessibilidade(html)


# Edição


def test_editar_o_pedido_pela_tela(client, colaborador, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    entrar(client, colaborador)
    pagina = client.get(reverse("agenda:pedido", args=[ag.pk]))
    assert pagina.status_code == 200
    verificar_acessibilidade(pagina.content.decode())
    resposta = client.post(reverse("agenda:pedido", args=[ag.pk]), {"foco_regioes": ["joelhos"], "observacao": "só hoje"}, follow=True)
    assert "Pedido para a sessão salvo" in resposta.content.decode()
    ag.refresh_from_db()
    assert ag.foco_regioes == ["joelhos"] and ag.observacao == "só hoje"


def test_pedido_de_outra_pessoa_da_404(client, colaborador, colaborador2, massoterapeuta, amanha):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha)
    entrar(client, colaborador2)
    assert client.get(reverse("agenda:pedido", args=[ag.pk])).status_code == 404
    assert client.post(reverse("agenda:pedido", args=[ag.pk]), {"observacao": "x"}).status_code == 404


def test_depois_do_checkin_abrir_a_tela_recusa_e_some_o_link(client, colaborador, massoterapeuta):
    from django.utils import timezone

    inicio = timezone.now().replace(microsecond=0) + timedelta(minutes=90)
    ag = Agendamento.objects.create(colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20))
    entrar(client, colaborador)
    resposta = client.post(reverse("agenda:pedido", args=[ag.pk]), {"observacao": "tarde"}, follow=True)
    assert "não pode mais ser mudado" in resposta.content.decode()
    ag.refresh_from_db()
    assert ag.observacao == ""
    assert reverse("agenda:pedido", args=[ag.pk]) not in client.get(reverse("agenda:meus_agendamentos")).content.decode()


# Encaixe pelo administrador


def test_encaixe_do_administrador_aceita_pedido_opcional(client, administrador, massoterapeuta, colaborador, segunda):
    entrar(client, administrador)
    tela = client.get(reverse("agenda:administrador_agendar"), {"colaborador": colaborador.pk, "dia": segunda.isoformat()})
    assert "Pedido da pessoa para esta sessão" in tela.content.decode()
    verificar_acessibilidade(tela.content.decode())
    client.post(
        reverse("agenda:administrador_agendar"),
        {
            "colaborador": colaborador.pk, "dia": segunda.isoformat(), "horario": "encaixe",
            "m_encaixe": massoterapeuta.pk, "hora_encaixe": "08:20",
            "foco_regioes": ["lombar"], "observacao": "pediu pelo telefone",
        },
    )
    ag = Agendamento.objects.get()
    assert ag.origem == "encaixe" and ag.foco_regioes == ["lombar"] and ag.observacao == "pediu pelo telefone"


def test_encaixe_sem_pedido_continua_valendo(client, administrador, massoterapeuta, colaborador, segunda):
    entrar(client, administrador)
    client.post(
        reverse("agenda:administrador_agendar"),
        {"colaborador": colaborador.pk, "dia": segunda.isoformat(), "horario": "encaixe", "m_encaixe": massoterapeuta.pk, "hora_encaixe": "08:20"},
    )
    assert Agendamento.objects.get().observacao == ""


def test_administrador_ve_a_observacao_e_so_a_situacao_da_ficha(client, administrador, massoterapeuta, colaborador, amanha):
    from apps.ficha import servicos as ficha

    ficha.salvar_ficha(colaborador, {"condicoes": ["gestacao"], "evitar": "texto-secreto"}, True)
    ag = servicos.agendar(colaborador, massoterapeuta, amanha, foco_regioes=["ombros"], observacao="quero ombros")
    entrar(client, administrador)
    html = client.get(reverse("agenda:administrador_agendamento", args=[ag.pk])).content.decode()
    assert "quero ombros" in html and "ombros" in html
    assert "Preenchida e atualizada" in html
    assert "gestação" not in html.lower() and "texto-secreto" not in html
    verificar_acessibilidade(html)
