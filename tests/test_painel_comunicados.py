from datetime import timedelta

import pytest
from django.urls import reverse

from apps.agenda import servicos
from apps.comunicados.models import Comunicado
from apps.notificacoes.models import InscricaoPush, Notificacao
from apps.painel import indicadores

from .test_telas import entrar, verificar_acessibilidade


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


@pytest.fixture
def semana_movimentada(massoterapeuta, colaborador, colaborador2, recepcao, segunda, em, cedo):
    """Segunda: Ana atendida, Bruno faltou. Terça: Ana cancelou."""
    atendida = servicos.agendar(colaborador, massoterapeuta, em(segunda, 8), agora=cedo)
    servicos.marcar_realizado(atendida, agora=em(segunda, 8, 5))
    falta = servicos.agendar(colaborador2, massoterapeuta, em(segunda, 8, 40), agora=cedo, por=recepcao)
    servicos.marcar_falta(falta, agora=em(segunda, 8, 50))
    cancelada = servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=1), 8), agora=cedo)
    servicos.cancelar(cancelada, por=colaborador, agora=cedo)


def test_indicadores_do_periodo(unidade, semana_movimentada, segunda):
    dados = indicadores.resumo(unidade, segunda, segunda + timedelta(days=6))
    geral = dados["geral"]
    assert geral.oferecidos == 12 * 7
    assert (geral.realizados, geral.faltas, geral.cancelados) == (1, 1, 1)
    assert geral.reservados == 2
    assert geral.taxa_faltas == 50
    assert geral.encaixes == 1
    assert dados["usuarios_unicos"] == 1


def test_folga_reduz_horarios_oferecidos(massoterapeuta, unidade, segunda, em):
    servicos.marcar_ausencia(
        massoterapeuta, em(segunda, 0), em(segunda + timedelta(days=1), 0), "folga", por=massoterapeuta.usuario,
        agora=em(segunda, 0) - timedelta(days=1),
    )
    assert indicadores.resumo(unidade, segunda, segunda)["geral"].oferecidos == 0


def test_tela_do_painel_e_csv(client, recepcao, semana_movimentada, segunda):
    entrar(client, recepcao)
    filtros = {"de": segunda.isoformat(), "ate": (segunda + timedelta(days=6)).isoformat()}
    html = client.get(reverse("painel:inicio"), filtros).content.decode()
    assert "massagens feitas" in html and "<caption" in html
    verificar_acessibilidade(html)

    csv = client.get(reverse("painel:csv_agendamentos"), filtros).content.decode("utf-8-sig")
    linhas = csv.strip().splitlines()
    assert linhas[0].startswith("Data;Hora;Massoterapeuta")
    assert len(linhas) == 4
    assert "Faltou" in csv and "Pela recepção" in csv

    resumo = client.get(reverse("painel:csv_resumo"), filtros).content.decode("utf-8-sig")
    assert "Carlos;84;2;" in resumo


def test_tela_de_historico(client, recepcao, semana_movimentada, segunda):
    entrar(client, recepcao)
    hoje = segunda - timedelta(days=7)
    filtros = {"de": hoje.isoformat(), "ate": (segunda + timedelta(days=6)).isoformat()}
    html = client.get(reverse("painel:historico"), filtros).content.decode()
    assert "Marcou falta" in html and "Agendou pela recepção" in html
    verificar_acessibilidade(html)


# Comunicados


def test_comunicado_para_massoterapeutas(client, recepcao, massoterapeuta, colaborador):
    InscricaoPush.objects.create(usuario=massoterapeuta.usuario, endpoint="https://push.exemplo.com/1", p256dh="p", auth="a")
    entrar(client, recepcao)
    verificar_acessibilidade(client.get(reverse("comunicados:novo")).content.decode())
    resposta = client.post(
        reverse("comunicados:novo"),
        {"titulo": "Sala nova", "texto": "A partir de segunda, a sala é a 12.", "publico": "massoterapeutas",
         "ativo": "on", "avisar": "on"},
        follow=True,
    )
    html = resposta.content.decode()
    assert "Comunicado publicado. Aviso enviado para 1 pessoa" in html
    verificar_acessibilidade(html)
    assert Notificacao.objects.filter(usuario=massoterapeuta.usuario, tipo=Notificacao.Tipo.COMUNICADO).exists()

    client.logout()
    entrar(client, massoterapeuta.usuario)
    agora = client.get(reverse("agenda:agora")).content.decode()
    assert "1 comunicado novo" in agora
    lista = client.get(reverse("comunicados:lista")).content.decode()
    assert "Sala nova" in lista
    verificar_acessibilidade(lista)
    assert "comunicado novo" not in client.get(reverse("agenda:agora")).content.decode()

    client.logout()
    entrar(client, colaborador)
    assert "Sala nova" not in client.get(reverse("comunicados:lista")).content.decode()


def test_comunicado_para_todos_aparece_para_colaborador(client, colaborador, recepcao):
    Comunicado.objects.create(titulo="Massagem de graça", texto="Agende já.", publico="todos", autor=recepcao)
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    assert 'href="/comunicados/"' in html


# Páginas públicas


def test_como_funciona_publica_e_acessivel(client, unidade, massoterapeuta):
    html = client.get(reverse("como_funciona")).content.decode()
    assert "Até 2 massagens por semana" in html
    verificar_acessibilidade(html)


def test_preferencia_de_libras(client, colaborador):
    entrar(client, colaborador)
    client.post(
        reverse("contas:preferencias"),
        {"tamanho_texto": 100, "fonte": "padrao", "tema": "sistema", "fala_velocidade": 100, "libras": "on"},
    )
    html = client.get(reverse("acessibilidade")).content.decode()
    assert 'data-libras="1"' in html and "data-abrir-libras" in html
