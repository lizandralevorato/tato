"""Etapa (e): o massoterapeuta e a ficha, uma pessoa por vez."""

import re
from datetime import datetime, timedelta, timezone as fuso

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos as agenda
from apps.agenda.formatacao import hora as formatar_hora
from apps.agenda.models import Agendamento
from apps.ficha import servicos
from apps.ficha.models import AcessoFicha
from apps.notificacoes import avisos
from apps.notificacoes.models import Notificacao

from .test_telas import entrar, verificar_acessibilidade

Status = Agendamento.Status
# Segunda-feira, 12h em São Paulo: relógio fixo para os testes de janela de horário.
FIXO = datetime(2026, 11, 2, 15, 0, tzinfo=fuso.utc)


@pytest.fixture
def agora(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: FIXO)
    return FIXO


@pytest.fixture
def atendimento(colaborador, massoterapeuta, agora):
    def _criar(minutos, status=Status.CONFIRMADO, usuario=None, m=None, **extra):
        inicio = FIXO + timedelta(minutes=minutos)
        return Agendamento.objects.create(
            colaborador=usuario or colaborador, massoterapeuta=m or massoterapeuta, inicio=inicio,
            fim=inicio + timedelta(minutes=20), status=status, **extra,
        )

    return _criar


@pytest.fixture
def ficha_completa(colaborador):
    return servicos.salvar_ficha(
        colaborador,
        {
            "regioes": {"ombros": {"intensidade": "forte", "frequencia": "sempre"}, "lombar": {"intensidade": "leve", "frequencia": ""}},
            "condicoes": ["gestacao", "hernia_disco", "alergia_oleos"],
            "condicao_outra": "labirintite",
            "dor_cronica": True,
            "dor_cronica_descricao": "nos joelhos",
            "pressao": "leve",
            "evitar": "não encostar no pescoço",
            "observacoes": "tenho cócegas",
        },
        True,
    )[0]


def url(ag):
    return reverse("ficha:do_atendimento", args=[ag.pk])


# Janela de acesso


@pytest.mark.parametrize(
    "comeca_em_min, esperado",
    [(150, 403), (121, 403), (119, 200), (60, 200), (0, 200), (-59, 200), (-61, 403), (-300, 403)],
)
def test_so_de_2h_antes_ate_1h_depois_do_horario(client, massoterapeuta, atendimento, ficha_completa, comeca_em_min, esperado):
    """`comeca_em_min` é quanto falta para o atendimento começar (negativo = já começou)."""
    ag = atendimento(comeca_em_min)
    entrar(client, massoterapeuta.usuario)
    assert client.get(url(ag)).status_code == esperado

def test_atendimento_cancelado_liberado_ou_falta_nao_abre(client, massoterapeuta, atendimento, ficha_completa):
    entrar(client, massoterapeuta.usuario)
    for i, status in enumerate([Status.CANCELADO, Status.EXPIRADO, Status.FALTA]):
        ag = atendimento(30 + i * 40, status=status)
        assert client.get(url(ag)).status_code == 403


@pytest.mark.parametrize("status", [Status.AGENDADO, Status.CONFIRMADO, Status.CHEGOU, Status.REALIZADO])
def test_status_ativos_abrem(client, massoterapeuta, atendimento, ficha_completa, status):
    ag = atendimento(-10, status=status)
    entrar(client, massoterapeuta.usuario)
    assert client.get(url(ag)).status_code == 200


def test_massoterapeuta_so_abre_os_proprios_atendimentos(client, massoterapeuta, outro_massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10, m=outro_massoterapeuta)
    entrar(client, massoterapeuta.usuario)
    assert client.get(url(ag)).status_code == 404


def test_sem_ficha_nao_ha_pagina(client, massoterapeuta, atendimento):
    ag = atendimento(-10)
    entrar(client, massoterapeuta.usuario)
    assert client.get(url(ag)).status_code == 404


@pytest.mark.parametrize("quem", ["colaborador", "colaborador2", "administrador", "sesmt"])
def test_outros_perfis_nao_abrem_a_ficha_do_atendimento(client, request, atendimento, ficha_completa, quem):
    ag = atendimento(-10)
    entrar(client, request.getfixturevalue(quem))
    assert client.get(url(ag)).status_code == 403


def test_superusuario_administrador_tambem_nao_passa(client, administrador, atendimento, ficha_completa):
    administrador.is_superuser = administrador.is_staff = True
    administrador.save()
    ag = atendimento(-10)
    entrar(client, administrador)
    assert client.get(url(ag)).status_code == 403


def test_sem_login_vai_para_entrar(client, atendimento, ficha_completa):
    resposta = client.get(url(atendimento(-10)))
    assert resposta.status_code == 302 and reverse("contas:entrar") in resposta.url


# A página


def test_pagina_da_ficha_do_atendimento(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10, foco_regioes=["ombros"], observacao="hoje só ombros")
    entrar(client, massoterapeuta.usuario)
    resposta = client.get(url(ag))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    titulo = f"Ficha de Ana, atendimento às {formatar_hora(ag.inicio)}"
    assert f'<h1 id="titulo-ficha-atendimento" tabindex="-1" data-focar-ao-carregar>{titulo}</h1>' in html
    assert html.count("data-focar-ao-carregar") == 1
    assert f"<title>{titulo} | TATO</title>" in html
    assert f'href="{reverse("agenda:agora")}#atendimento-{ag.pk}"' in html and "Voltar para a agenda" in html
    assert "Ouvir ficha" in html and "Pausar" in html and "Repetir" in html
    assert "A ficha contém dados de saúde. Use fones se houver outras pessoas por perto." in html
    assert "no-store" in resposta["Cache-Control"]
    verificar_acessibilidade(html)


def test_ordem_das_secoes_alertas_foco_recorrentes_dor_pressao_evitar_observacoes(
    client, massoterapeuta, atendimento, ficha_completa, colaborador
):
    for dias in (1, 2, 3):
        atendimento(-60 * 24 * dias - 300, status=Status.REALIZADO, foco_regioes=["ombros"])
    ag = atendimento(-10, foco_regioes=["ombros"], observacao="hoje só ombros")
    entrar(client, massoterapeuta.usuario)
    html = client.get(url(ag)).content.decode()
    titulos = re.findall(r"<h2 id=\"secao-\d+\">([^<]+)</h2>", html)
    assert titulos == [
        "Alertas de atenção", "Foco desta sessão", "Regiões recorrentes", "Regiões com dor ou desconforto",
        "Outras informações de saúde", "Preferência de pressão", "O que evitar", "Observações",
    ]
    assert "Atenção: gestação (gravidez)." in html and "Atenção: alergia a óleos ou cremes." in html
    assert "Pedido da pessoa para esta sessão: hoje só ombros" in html
    assert "Região recorrente: ombros (4x em 30 dias)" in html


def test_a_ficha_aparece_inteira_mesmo_sem_pedido_para_a_sessao(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10)  # a pessoa não escreveu nada para esta massagem
    entrar(client, massoterapeuta.usuario)
    html = client.get(url(ag)).content.decode()
    assert "A pessoa não escolheu foco para esta sessão." in html
    for trecho in (
        "Ombros: intensidade forte, frequência sempre.", "Lombar: intensidade leve.", "Condições: hérnia de disco.",
        "Outra condição: labirintite.", "Dor crônica: sim. nos joelhos", "Prefere pressão leve.",
        "Evitar: não encostar no pescoço", "tenho cócegas",
    ):
        assert trecho in html, trecho


def test_ficha_so_para_leitura_sem_formulario(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10)
    entrar(client, massoterapeuta.usuario)
    html = client.get(url(ag)).content.decode()
    assert "<form" not in html.split('<main')[1] and "<textarea" not in html
    assert client.post(url(ag)).status_code == 405
    assert servicos.FichaSaude.objects.get().evitar == "não encostar no pescoço"


def test_cada_abertura_fica_registrada(client, massoterapeuta, atendimento, ficha_completa, colaborador, agora):
    ag = atendimento(-10)
    entrar(client, massoterapeuta.usuario)
    client.get(url(ag))
    client.get(url(ag))
    registros = list(AcessoFicha.objects.all())
    assert len(registros) == 2
    r = registros[0]
    assert (r.usuario, r.colaborador, r.agendamento, r.finalidade, r.em) == (
        massoterapeuta.usuario, colaborador, ag, AcessoFicha.Finalidade.ATENDIMENTO, agora,
    )
    assert r.usuario_nome == "Carlos" and r.colaborador_nome == "Ana"


def test_acesso_negado_nao_registra(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-300)
    entrar(client, massoterapeuta.usuario)
    assert client.get(url(ag)).status_code == 403
    assert not AcessoFicha.objects.exists()


# Aviso de fones


def test_aviso_de_fones_pode_ser_ocultado_para_sempre(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10)
    entrar(client, massoterapeuta.usuario)
    assert 'data-mostrar-aviso="1"' in client.get(url(ag)).content.decode()
    assert client.get(reverse("ficha:ocultar_aviso_fala")).status_code == 405
    assert client.post(reverse("ficha:ocultar_aviso_fala")).status_code == 204
    assert 'data-mostrar-aviso="0"' in client.get(url(ag)).content.decode()


def test_so_massoterapeuta_oculta_o_aviso(client, colaborador):
    entrar(client, colaborador)
    assert client.post(reverse("ficha:ocultar_aviso_fala")).status_code == 403


# A lista do dia


def _agenda(client, massoterapeuta):
    entrar(client, massoterapeuta.usuario)
    return client.get(reverse("agenda:agora")).content.decode()


def test_lista_mostra_foco_recorrencia_pedido_e_o_botao_com_nome_e_horario(client, massoterapeuta, atendimento, ficha_completa):
    for dias in (1, 2, 3):
        atendimento(-60 * 24 * dias - 300, status=Status.REALIZADO, foco_regioes=["ombros"])
    ag = atendimento(-10, foco_regioes=["ombros"], observacao="hoje só ombros")
    html = _agenda(client, massoterapeuta)
    assert "Foco hoje: ombros. Região recorrente: ombros (4x em 30 dias). Pedido da pessoa: “hoje só ombros”." in html
    assert f'href="{url(ag)}"' in html
    assert f'Ver ficha<span class="sr-only"> de Ana, {formatar_hora(ag.inicio)}</span>' in html
    assert f'id="atendimento-{ag.pk}" tabindex="-1"' in html


def test_lista_nunca_mostra_o_conteudo_da_ficha(client, massoterapeuta, atendimento, ficha_completa):
    atendimento(-10, foco_regioes=["ombros"])
    html = _agenda(client, massoterapeuta).lower()
    for segredo in ("gestação", "hérnia", "labirintite", "alergia", "cócegas", "joelhos", "não encostar", "pressão leve"):
        assert segredo not in html, segredo
    assert "a ficha tem alertas de atenção. abra a ficha antes de começar." in html


def test_alerta_generico_so_aparece_quando_ha_alerta(client, massoterapeuta, atendimento, colaborador):
    servicos.salvar_ficha(colaborador, {"condicoes": ["hernia_disco"]}, True)
    atendimento(-10)
    assert "tem alertas" not in _agenda(client, massoterapeuta)


def test_sem_ficha_aparece_o_texto_e_nao_o_botao(client, massoterapeuta, atendimento):
    ag = atendimento(-10, observacao="só o pedido")
    html = _agenda(client, massoterapeuta)
    assert "Sem ficha preenchida." in html and "Ver ficha<span" not in html
    assert "Pedido da pessoa: “só o pedido”." in html  # o pedido da sessão chega mesmo sem ficha
    assert url(ag) not in html


def test_antes_da_janela_nao_tem_botao_e_diz_quando_abre(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(200)  # começa daqui a 3h20
    html = _agenda(client, massoterapeuta)
    assert "Ver ficha<span" not in html and url(ag) not in html
    assert f"Você poderá abrir a partir das {formatar_hora(ag.inicio - timedelta(minutes=120))}." in html
    assert "alertas" not in html


def test_cancelado_some_da_lista_e_a_observacao_nao_aparece(client, massoterapeuta, atendimento, ficha_completa):
    atendimento(-10, status=Status.CANCELADO, observacao="observacao-cancelada", foco_regioes=["pescoco"])
    html = _agenda(client, massoterapeuta)
    assert "observacao-cancelada" not in html
    assert Agendamento.objects.get().observacao == "observacao-cancelada"  # continua guardada no histórico


def test_agenda_do_dia_continua_acessivel(client, massoterapeuta, atendimento, ficha_completa):
    atendimento(-10, foco_regioes=["ombros"])
    atendimento(30)
    verificar_acessibilidade(_agenda(client, massoterapeuta))


# Voz e avisos


def test_ouvir_agenda_fala_horario_nome_e_foco_e_nunca_saude(client, massoterapeuta, atendimento, ficha_completa):
    ag = atendimento(-10, foco_regioes=["ombros", "lombar"], observacao="texto livre privado")
    html = _agenda(client, massoterapeuta)
    falado = re.search(r'data-texto-falado="([^"]*)"', html).group(1)
    assert f"{formatar_hora(ag.inicio)}, Ana, check-in feito. Foco: ombros e lombar." in falado
    assert "Para ouvir a ficha de alguém, use o botão Ver ficha no atendimento." in falado
    for proibido in ("gestação", "hérnia", "dor", "pressão", "privado", "alerta", "recorrente"):
        assert proibido not in falado.lower()


def test_estado_json_so_leva_o_foco(client, massoterapeuta, atendimento, ficha_completa):
    atendimento(-10, foco_regioes=["ombros"], observacao="texto livre privado")
    entrar(client, massoterapeuta.usuario)
    bruto = client.get(reverse("agenda:estado_json")).content.decode()
    item = client.get(reverse("agenda:estado_json")).json()["itens"][0]
    assert item["foco"] == "ombros"
    for proibido in ("privado", "gestacao", "gestação", "hernia"):
        assert proibido not in bruto


def test_estado_json_nao_leva_o_foco_de_atendimento_cancelado(client, massoterapeuta, atendimento):
    atendimento(-10, status=Status.CANCELADO, foco_regioes=["ombros"], observacao="cancelada")
    entrar(client, massoterapeuta.usuario)
    [item] = client.get(reverse("agenda:estado_json")).json()["itens"]
    assert item["status"] == "cancelado" and item["foco"] == ""


def test_versao_da_agenda_muda_quando_a_ficha_libera_e_quando_o_pedido_muda(massoterapeuta, atendimento, ficha_completa, monkeypatch):
    from apps.agenda.views.massoterapeuta import _estado

    ag = atendimento(150)  # a ficha ainda não abriu
    antes = _estado(massoterapeuta)["versao"]
    monkeypatch.setattr(timezone, "now", lambda: FIXO + timedelta(minutes=40))  # agora faltam 110 min
    assert _estado(massoterapeuta)["versao"] != antes
    depois = _estado(massoterapeuta)["versao"]
    ag.foco_regioes, ag.observacao_em = ["pescoco"], FIXO
    ag.save()
    assert _estado(massoterapeuta)["versao"] != depois


def test_notificacao_nunca_leva_texto_livre_nem_saude(massoterapeuta, colaborador, ficha_completa, em):
    hoje = timezone.localdate()
    inicio = em(hoje, 23, 50)
    ag = Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
        foco_regioes=["ombros"], observacao="texto livre sigiloso",
    )
    avisos.ao_agendar(ag)
    avisos.ao_chegar(ag)
    avisos.proximo_atendimento(ag, 5)
    assert Notificacao.objects.exists()
    for n in Notificacao.objects.all():
        texto = f"{n.titulo} {n.corpo}".lower()
        assert "sigiloso" not in texto and "gestação" not in texto and "ombros" not in texto


# Regras (sem tela)


def test_janela_de_acesso_nas_regras(massoterapeuta, colaborador, atendimento):
    ag = atendimento(0)
    abre, fecha = servicos.janela_de_acesso(ag)
    assert (abre, fecha) == (ag.inicio - timedelta(hours=2), ag.inicio + timedelta(hours=1))
    assert servicos.na_janela_de_acesso(ag, abre) and servicos.na_janela_de_acesso(ag, fecha)
    assert not servicos.na_janela_de_acesso(ag, abre - timedelta(seconds=1))
    assert not servicos.na_janela_de_acesso(ag, fecha + timedelta(seconds=1))
