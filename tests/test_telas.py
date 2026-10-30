"""Testes das telas: permissões, fluxo principal e checagens básicas de acessibilidade.

As checagens de HTML aqui NÃO substituem o axe-core nem o teste com leitores de
tela; elas garantem que regras estruturais não quebrem sem ninguém perceber.
"""

from datetime import timedelta
from html.parser import HTMLParser

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import Agendamento

from .conftest import SENHA


class AnalisadorHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pilha_labels = 0
        self.lang = None
        self.titulo = ""
        self._no_titulo = False
        self.h1 = 0
        self.ids = []
        self.labels_for = set()
        self.campos = []  # (id, dentro_de_label, attrs)
        self.imagens_sem_alt = 0
        self.links_pular = 0
        self.main_conteudo = False
        self.viewport = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._no_titulo = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "label":
            self.pilha_labels += 1
            if a.get("for"):
                self.labels_for.add(a["for"])
        elif tag in {"input", "select", "textarea"} and a.get("type") not in {"hidden", "submit", "button"}:
            self.campos.append((a.get("id"), self.pilha_labels > 0, a))
        elif tag == "img" and "alt" not in a:
            self.imagens_sem_alt += 1
        elif tag == "a" and a.get("href") == "#conteudo":
            self.links_pular += 1
        elif tag == "main" and a.get("id") == "conteudo":
            self.main_conteudo = True
        elif tag == "meta" and a.get("name") == "viewport":
            self.viewport = a.get("content", "")

    def handle_endtag(self, tag):
        if tag == "label":
            self.pilha_labels -= 1
        elif tag == "title":
            self._no_titulo = False

    def handle_data(self, data):
        if self._no_titulo:
            self.titulo += data


def verificar_acessibilidade(html):
    p = AnalisadorHTML()
    p.feed(html)
    assert p.lang == "pt-BR"
    assert p.titulo.strip() and not p.titulo.strip().startswith("|"), "página sem título próprio"
    assert p.h1 == 1, f"esperado 1 <h1>, encontrado {p.h1}"
    assert p.links_pular == 1, "falta o link 'Pular para o conteúdo'"
    assert p.main_conteudo, "falta <main id='conteudo'>"
    assert p.imagens_sem_alt == 0
    assert "user-scalable=no" not in p.viewport and "maximum-scale" not in p.viewport, "zoom bloqueado"
    duplicados = {i for i in p.ids if p.ids.count(i) > 1}
    assert not duplicados, f"ids duplicados: {duplicados}"
    for id_, dentro_de_label, attrs in p.campos:
        tem_rotulo = dentro_de_label or (id_ in p.labels_for) or attrs.get("aria-label") or attrs.get("aria-labelledby")
        assert tem_rotulo, f"campo sem rótulo: {attrs}"


def entrar(client, usuario):
    assert client.login(email=usuario.email, password=SENHA)


@pytest.fixture
def amanha_8h(em):
    return em(timezone.localdate() + timedelta(days=1), 8)


# Acesso
def test_sem_login_vai_para_entrar(client, db):
    resposta = client.get(reverse("agenda:meus_agendamentos"))
    assert resposta.status_code == 302
    assert reverse("contas:entrar") in resposta.url


def test_pagina_entrar_acessivel(client, db):
    resposta = client.get(reverse("contas:entrar"))
    assert resposta.status_code == 200
    verificar_acessibilidade(resposta.content.decode())


def test_login_com_erro_mostra_resumo(client, colaborador):
    resposta = client.post(reverse("contas:entrar"), {"username": colaborador.email, "password": "errada"})
    html = resposta.content.decode()
    assert "resumo-erros" in html and "E-mail ou senha incorretos" in html
    verificar_acessibilidade(html)


def test_colaborador_nao_acessa_tela_do_massoterapeuta(client, colaborador):
    entrar(client, colaborador)
    assert client.get(reverse("agenda:agora")).status_code == 403


def test_massoterapeuta_nao_acessa_administrador(client, massoterapeuta):
    entrar(client, massoterapeuta.usuario)
    assert client.get(reverse("agenda:administrador")).status_code == 403


def test_primeiro_acesso_passa_pelas_preferencias(client, colaborador):
    colaborador.perfil_acessibilidade.configurado = False
    colaborador.perfil_acessibilidade.save()
    entrar(client, colaborador)
    resposta = client.get(reverse("inicio"))
    assert resposta.url.startswith(reverse("contas:preferencias"))


# Páginas renderizam e passam nas checagens
@pytest.mark.parametrize(
    "nome_url",
    ["agenda:meus_agendamentos", "agenda:agendar_dia", "contas:preferencias", "acessibilidade"],
)
def test_paginas_do_colaborador(client, colaborador, massoterapeuta, nome_url):
    entrar(client, colaborador)
    resposta = client.get(reverse(nome_url))
    assert resposta.status_code == 200
    verificar_acessibilidade(resposta.content.decode())


def test_pagina_de_horarios(client, colaborador, massoterapeuta, outro_massoterapeuta):
    entrar(client, colaborador)
    amanha = (timezone.localdate() + timedelta(days=1)).isoformat()
    resposta = client.get(reverse("agenda:agendar_horario", args=[amanha]))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "<fieldset>" in html and "<legend>Manhã" in html
    verificar_acessibilidade(html)


@pytest.mark.parametrize("nome_url", ["agenda:agora", "agenda:disponibilidade"])
def test_paginas_do_massoterapeuta(client, massoterapeuta, colaborador, amanha_8h, nome_url):
    entrar(client, massoterapeuta.usuario)
    resposta = client.get(reverse(nome_url))
    assert resposta.status_code == 200
    verificar_acessibilidade(resposta.content.decode())


def test_pagina_da_administrador(client, administrador, massoterapeuta, colaborador, amanha_8h):
    servicos.agendar(colaborador, massoterapeuta, amanha_8h)
    entrar(client, administrador)
    resposta = client.get(reverse("agenda:administrador") + f"?dia={amanha_8h.date().isoformat()}")
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "<caption" in html and 'scope="col"' in html
    verificar_acessibilidade(html)


@pytest.mark.parametrize("tema", ["claro", "escuro", "ac-escuro", "ac-claro"])
def test_preferencias_viram_classes_no_html(client, colaborador, tema):
    perfil = colaborador.perfil_acessibilidade
    perfil.tema, perfil.tamanho_texto, perfil.modo_simplificado = tema, 200, True
    perfil.save()
    entrar(client, colaborador)
    html = client.get(reverse("acessibilidade")).content.decode()
    assert f"tema-{tema}" in html and "texto-200" in html and "modo-simplificado" in html


# Fluxos
def test_fluxo_de_agendamento_completo(client, colaborador, massoterapeuta, amanha_8h):
    entrar(client, colaborador)
    confirmacao = client.get(reverse("agenda:agendar_confirmar"), {"inicio": amanha_8h.isoformat()})
    assert confirmacao.status_code == 200
    verificar_acessibilidade(confirmacao.content.decode())

    resposta = client.post(
        reverse("agenda:agendar_confirmar"),
        {"inicio": amanha_8h.isoformat(), "m": massoterapeuta.pk},
        follow=True,
    )
    html = resposta.content.decode()
    assert "Massagem agendada" in html
    assert 'data-focar-ao-carregar' in html
    assert Agendamento.objects.filter(colaborador=colaborador, inicio=amanha_8h).exists()


def test_salvar_preferencias(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(
        reverse("contas:preferencias"),
        {"tamanho_texto": 150, "fonte": "legivel", "tema": "ac-escuro", "fala_velocidade": 100, "lembrete_checkin_min": 30, "fala_ativa": "on"},
        follow=True,
    )
    assert "Preferências salvas" in resposta.content.decode()
    colaborador.perfil_acessibilidade.refresh_from_db()
    assert colaborador.perfil_acessibilidade.tema == "ac-escuro"
    assert colaborador.perfil_acessibilidade.fala_ativa is True


def test_estado_json_do_massoterapeuta(client, colaborador, massoterapeuta, em):
    hoje_tarde = em(timezone.localdate(), 23, 59)
    Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=hoje_tarde - timedelta(minutes=20), fim=hoje_tarde
    )
    entrar(client, massoterapeuta.usuario)
    dados = client.get(reverse("agenda:estado_json")).json()
    assert dados["versao"]
    assert dados["itens"][0]["nome"] == "Ana"
    assert client.get(reverse("agenda:agora_parcial")).status_code == 200


def test_colaborador_nao_cancela_agendamento_de_outro(client, colaborador, colaborador2, massoterapeuta, amanha_8h):
    ag = servicos.agendar(colaborador, massoterapeuta, amanha_8h)
    entrar(client, colaborador2)
    assert client.post(reverse("agenda:cancelar", args=[ag.pk])).status_code == 404


def test_datas_sempre_em_portugues_mesmo_com_navegador_em_ingles(client, colaborador, massoterapeuta, amanha_8h):
    servicos.agendar(colaborador, massoterapeuta, amanha_8h)
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9").content.decode()
    assert "Amanhã" in html
    assert "day," not in html  # Monday, Tuesday...


# Check-in pela tela
def _agendamento_em(colaborador, massoterapeuta, minutos):
    inicio = timezone.now().replace(microsecond=0) + timedelta(minutes=minutos)
    return Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20)
    )


def test_botao_fazer_checkin_aparece_na_janela_e_funciona(client, colaborador, massoterapeuta):
    ag = _agendamento_em(colaborador, massoterapeuta, 90)
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    assert "Fazer check-in" in html and "a reserva é liberada para outra pessoa" in html
    verificar_acessibilidade(html)

    resposta = client.post(reverse("agenda:checkin", args=[ag.pk]), follow=True)
    assert "Check-in feito" in resposta.content.decode()
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.CONFIRMADO


def test_reserva_sem_checkin_some_dos_proximos_e_aparece_no_historico(client, colaborador, massoterapeuta):
    ag = _agendamento_em(colaborador, massoterapeuta, 30)  # prazo + tolerância já passaram
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.EXPIRADO
    assert "Você não tem massagens marcadas." in html
    assert "Liberado (sem check-in)" in html


def test_regra_do_checkin_aparece_no_modo_simplificado(client, colaborador, massoterapeuta):
    perfil = colaborador.perfil_acessibilidade
    perfil.modo_simplificado = True
    perfil.save()
    _agendamento_em(colaborador, massoterapeuta, 60 * 26)  # amanhã: check-in ainda fechado
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    trecho = html[html.index("Check-in: das"):][:200]
    inicio_do_bloco = html.rfind("<p", 0, html.index("Check-in: das"))
    assert "secundario" not in html[inicio_do_bloco:html.index("Check-in: das")], trecho
