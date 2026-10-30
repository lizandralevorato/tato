import json
from datetime import timedelta

import pytest
import requests
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from pywebpush import WebPushException

from apps.agenda import servicos
from apps.agenda.models import Agendamento
from apps.notificacoes import avisos, push, tarefas, tokens
from apps.notificacoes.models import InscricaoPush, Notificacao

from .test_telas import entrar, verificar_acessibilidade

Tipo = Notificacao.Tipo


class RespostaFalsa:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


@pytest.fixture
def enviados(monkeypatch, settings):
    """Troca o envio real por uma lista, com chaves VAPID de teste."""
    settings.VAPID_PUBLIC_KEY = "chave-publica-de-teste"
    settings.VAPID_PRIVATE_KEY = "chave-privada-de-teste"
    lista = []

    def webpush_falso(subscription_info, data, **kwargs):
        lista.append({"para": subscription_info["endpoint"], "dados": json.loads(data), **kwargs})

    monkeypatch.setattr(push, "webpush", webpush_falso)
    return lista


def inscrever(usuario, n=1):
    return InscricaoPush.objects.create(
        usuario=usuario, endpoint=f"https://push.exemplo.com/{usuario.pk}/{n}", p256dh="p", auth="a"
    )


@pytest.fixture
def cedo(segunda, em):
    return em(segunda, 7) - timedelta(hours=12)


@pytest.fixture
def hoje_tarde(colaborador, massoterapeuta, em):
    """Agendamento de hoje, no fim do dia (não depende da hora em que o teste roda)."""
    inicio = em(timezone.localdate(), 23, 30)
    return Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20)
    )


# Avisos ao massoterapeuta
def test_chegada_avisa_o_massoterapeuta_com_urgencia(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(massoterapeuta.usuario)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        servicos.avisar_chegada(ag, agora=em(segunda, 9, 15))

    assert len(enviados) == 1
    envio = enviados[0]
    assert envio["dados"]["corpo"] == "Ana chegou. Atendimento das 9h20."
    assert envio["dados"]["tipo"] == "chegada"
    assert envio["dados"]["vibrar"] == [150, 100, 150]
    assert envio["headers"]["Urgency"] == "high"
    assert Notificacao.objects.get(tipo=Tipo.CHEGADA).enviada_em is not None


def test_sem_vibracao_nas_preferencias_nao_vibra(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    massoterapeuta.usuario.perfil_acessibilidade.vibracao = False
    massoterapeuta.usuario.perfil_acessibilidade.save()
    inscrever(massoterapeuta.usuario)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 9, 20), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        servicos.avisar_chegada(ag, agora=em(segunda, 9, 15))
    assert enviados[0]["dados"]["vibrar"] == []


def test_agendamento_de_hoje_avisa_e_de_outro_dia_nao(
    massoterapeuta, colaborador, hoje_tarde, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(massoterapeuta.usuario)
    with django_capture_on_commit_callbacks(execute=True):
        servicos.agendar(colaborador, massoterapeuta, em(segunda + timedelta(days=1), 8), agora=cedo)
        avisos.ao_agendar(hoje_tarde)
    assert [e["dados"]["tipo"] for e in enviados] == ["novo"]
    assert "23h30" in enviados[0]["dados"]["corpo"]


def test_cancelamento_pela_administrador_avisa_os_dois(
    massoterapeuta, colaborador, administrador, hoje_tarde, enviados, django_capture_on_commit_callbacks
):
    inscrever(massoterapeuta.usuario)
    inscrever(colaborador)
    with django_capture_on_commit_callbacks(execute=True):
        servicos.cancelar(hoje_tarde, por=administrador)
    destinos = {e["para"] for e in enviados}
    assert destinos == {f"https://push.exemplo.com/{massoterapeuta.usuario.pk}/1", f"https://push.exemplo.com/{colaborador.pk}/1"}
    textos = " ".join(e["dados"]["corpo"] for e in enviados)
    assert "O horário ficou livre" in textos and "O administrador cancelou" in textos


def test_cancelamento_pelo_proprio_colaborador_so_avisa_o_massoterapeuta(
    massoterapeuta, colaborador, hoje_tarde, enviados, django_capture_on_commit_callbacks
):
    inscrever(massoterapeuta.usuario)
    inscrever(colaborador)
    with django_capture_on_commit_callbacks(execute=True):
        servicos.cancelar(hoje_tarde, por=colaborador, agora=hoje_tarde.inicio - timedelta(hours=1))
    assert [e["para"] for e in enviados] == [f"https://push.exemplo.com/{massoterapeuta.usuario.pk}/1"]


# Falhas de envio
def test_aparelho_que_saiu_e_removido(massoterapeuta, colaborador, hoje_tarde, monkeypatch, settings):
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = "x"
    inscrever(massoterapeuta.usuario)

    def expirado(**kwargs):
        raise WebPushException("Gone", response=RespostaFalsa(410))

    monkeypatch.setattr(push, "webpush", lambda subscription_info, data, **kw: expirado())
    notificacao = avisos.ao_chegar(hoje_tarde)
    assert push.enviar(notificacao) is False
    assert not InscricaoPush.objects.exists()


def test_sem_chaves_vapid_registra_e_nao_quebra(massoterapeuta, colaborador, hoje_tarde, settings):
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = ""
    inscrever(massoterapeuta.usuario)
    notificacao = avisos.ao_chegar(hoje_tarde)
    assert push.enviar(notificacao) is False
    notificacao.refresh_from_db()
    assert "VAPID" in notificacao.erro


def test_falha_de_rede_e_reenviada_no_proximo_ciclo(massoterapeuta, colaborador, hoje_tarde, monkeypatch, settings):
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = "x"
    inscrever(massoterapeuta.usuario)
    tentativas = []

    def instavel(subscription_info, data, **kwargs):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise requests.ConnectionError("sem internet")

    monkeypatch.setattr(push, "webpush", instavel)
    notificacao = avisos.ao_chegar(hoje_tarde)
    assert push.enviar(notificacao) is False
    assert tarefas.reenviar_falhas() == 1
    notificacao.refresh_from_db()
    assert notificacao.enviada_em is not None and notificacao.tentativas == 2


def test_erro_inesperado_nao_derruba_quem_chamou(massoterapeuta, colaborador, hoje_tarde, monkeypatch, settings):
    settings.VAPID_PUBLIC_KEY = settings.VAPID_PRIVATE_KEY = "x"
    inscrever(massoterapeuta.usuario)
    monkeypatch.setattr(push, "webpush", lambda **kw: 1 / 0)
    assert push.enviar(avisos.ao_chegar(hoje_tarde)) is False


# Check-in: lembrete, último aviso e liberação (tarefa periódica)
def test_lembrete_sai_quando_o_checkin_abre_e_uma_vez_so(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(colaborador)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        assert tarefas.enviar_lembretes(agora=em(segunda, 7, 50)) == 0  # check-in ainda fechado
        assert tarefas.enviar_lembretes(agora=em(segunda, 8, 1)) == 1
        assert tarefas.enviar_lembretes(agora=em(segunda, 8, 2)) == 0  # não repete

    dados = enviados[0]["dados"]
    assert dados["tipo"] == "lembrete"
    assert "às 10h, com Carlos" in dados["corpo"]
    assert "Faça o check-in até 9h. Sem check-in até 9h05, a reserva é liberada" in dados["corpo"]
    assert [a["titulo"] for a in dados["acoes"]] == ["Fazer check-in", "Não vou"]
    assert tokens.ler(dados["url"].split("/")[2]) == ag.pk


def test_lembrete_respeita_o_tempo_escolhido_nas_preferencias(massoterapeuta, colaborador, segunda, em, cedo):
    colaborador.perfil_acessibilidade.lembrete_checkin_min = 30
    colaborador.perfil_acessibilidade.save()
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 29)) == 0  # prazo 9h, 30 min antes = 8h30
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 31)) == 1


def test_lembrete_antes_do_checkin_abrir_avisa_o_horario_de_abertura(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(colaborador)
    colaborador.perfil_acessibilidade.lembrete_checkin_min = 180
    colaborador.perfil_acessibilidade.save()
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        assert tarefas.enviar_lembretes(agora=em(segunda, 5, 59)) == 0
        assert tarefas.enviar_lembretes(agora=em(segunda, 6, 1)) == 1
    assert "O check-in abre às 8h e vai até 9h." in enviados[0]["dados"]["corpo"]


def test_lembrete_nao_vai_para_quem_ja_fez_checkin(massoterapeuta, colaborador, segunda, em, cedo):
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    servicos.fazer_checkin(ag, agora=em(segunda, 8))
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 1)) == 0
    assert tarefas.avisar_prazo_checkin(agora=em(segunda, 9, 1)) == 0


def test_checkin_desligado_nao_manda_lembrete(massoterapeuta, colaborador, segunda, em, cedo):
    politica = servicos.politica_da(massoterapeuta.unidade)
    politica.checkin_prazo_min = 0
    politica.save()
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    assert tarefas.enviar_lembretes(agora=em(segunda, 8, 30)) == 0


def test_ultimo_aviso_no_prazo_do_checkin(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(colaborador)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        assert tarefas.avisar_prazo_checkin(agora=em(segunda, 8, 59)) == 0  # ainda antes do prazo
        assert tarefas.avisar_prazo_checkin(agora=em(segunda, 9, 1)) == 1
        assert tarefas.avisar_prazo_checkin(agora=em(segunda, 9, 3)) == 0  # não repete

    dados = enviados[0]["dados"]
    assert dados["tipo"] == "ultimo_aviso" and dados["urgente"] is True
    assert dados["corpo"] == "Faça o check-in até 9h05 ou sua massagem das 10h será liberada para outra pessoa."
    assert [a["id"] for a in dados["acoes"]] == ["vou", "nao-vou"]


def test_ciclo_libera_e_avisa_a_pessoa(
    massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks
):
    inscrever(colaborador)
    ag = servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        resultado = tarefas.rodar_ciclo(agora=em(segunda, 9, 6))
    assert resultado["liberadas"] == 1
    assert resultado["ultimos_avisos"] == 0  # quem já perdeu o prazo não recebe "último aviso"
    ag.refresh_from_db()
    assert ag.status == Agendamento.Status.EXPIRADO
    assert [e["dados"]["tipo"] for e in enviados] == ["liberado"]
    assert "foi liberada porque o check-in não foi feito a tempo" in enviados[0]["dados"]["corpo"]


def test_liberacao_de_hoje_tambem_avisa_o_massoterapeuta(
    massoterapeuta, colaborador, hoje_tarde, enviados, django_capture_on_commit_callbacks
):
    inscrever(colaborador)
    inscrever(massoterapeuta.usuario)
    with django_capture_on_commit_callbacks(execute=True):
        avisos.ao_liberar(hoje_tarde)
    corpos = {e["para"].split("/")[3]: e["dados"]["corpo"] for e in enviados}
    assert corpos[str(massoterapeuta.usuario.pk)] == "Liberado: 23h30, Ana não fez check-in. O horário está livre."
    assert enviados[0]["dados"]["vibrar"] == [600]


def test_aviso_de_proximo_atendimento(massoterapeuta, colaborador, segunda, em, cedo, enviados, django_capture_on_commit_callbacks):
    inscrever(massoterapeuta.usuario)
    servicos.agendar(colaborador, massoterapeuta, em(segunda, 10), agora=cedo)
    with django_capture_on_commit_callbacks(execute=True):
        assert tarefas.avisar_proximos(agora=em(segunda, 9, 50)) == 0
        assert tarefas.avisar_proximos(agora=em(segunda, 9, 56)) == 1
        assert tarefas.avisar_proximos(agora=em(segunda, 9, 58)) == 0
    assert enviados[0]["dados"]["corpo"].startswith("Próximo atendimento em 4 minutos: 10h, Ana")


def test_comando_roda_um_ciclo(db, capsys):
    call_command("notificacoes")
    assert "lembretes=0" in capsys.readouterr().out


# Página do lembrete (link assinado, sem login)
@pytest.fixture
def ag_amanha(colaborador, massoterapeuta, em):
    return servicos.agendar(colaborador, massoterapeuta, em(timezone.localdate() + timedelta(days=1), 10))


def test_pagina_do_lembrete_acessivel_e_sem_login(client, ag_amanha):
    resposta = client.get(reverse("notificacoes:lembrete", args=[tokens.gerar(ag_amanha)]))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'value="nao-vou"' in html  # check-in ainda fechado: só dá para cancelar
    verificar_acessibilidade(html)


@pytest.fixture
def ag_com_checkin_aberto(colaborador, massoterapeuta):
    """Daqui a 1 h 30: check-in aberto (abre 2 h antes), prazo em 30 min."""
    inicio = timezone.now().replace(microsecond=0) + timedelta(minutes=90)
    return Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20)
    )


def test_lembrete_com_checkin_aberto_mostra_os_dois_botoes(client, ag_com_checkin_aberto):
    html = client.get(reverse("notificacoes:lembrete", args=[tokens.gerar(ag_com_checkin_aberto)])).content.decode()
    assert "Fazer check-in" in html and 'value="nao-vou"' in html
    verificar_acessibilidade(html)


def test_lembrete_antes_de_abrir_so_permite_cancelar(client, ag_amanha):
    html = client.get(reverse("notificacoes:lembrete", args=[tokens.gerar(ag_amanha)])).content.decode()
    assert 'value="vou"' not in html and 'value="nao-vou"' in html
    assert "O check-in abre às 8h" in html


def test_lembrete_fazer_checkin(client, ag_com_checkin_aberto):
    url = reverse("notificacoes:lembrete", args=[tokens.gerar(ag_com_checkin_aberto)])
    resposta = client.post(url, {"acao": "vou"})
    assert resposta.status_code == 200
    ag_com_checkin_aberto.refresh_from_db()
    assert ag_com_checkin_aberto.status == Agendamento.Status.CONFIRMADO
    verificar_acessibilidade(resposta.content.decode())


def test_lembrete_depois_do_prazo_mostra_que_foi_liberada(client, colaborador, massoterapeuta):
    inicio = timezone.now() + timedelta(minutes=30)  # prazo + tolerância já passaram
    ag = Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20)
    )
    url = reverse("notificacoes:lembrete", args=[tokens.gerar(ag)])
    assert "Liberado (sem check-in)" in client.get(url).content.decode()
    resposta = client.post(url, {"acao": "vou"}, HTTP_ACCEPT="application/json")
    assert resposta.status_code == 409 and "reserva foi liberada" in resposta.json()["mensagem"]


def test_lembrete_nao_vou_cancela_e_responde_json_para_o_service_worker(client, ag_amanha):
    resposta = client.post(
        reverse("notificacoes:lembrete", args=[tokens.gerar(ag_amanha)]),
        {"acao": "nao-vou"},
        HTTP_ACCEPT="application/json",
    )
    assert resposta.json()["ok"] is True
    ag_amanha.refresh_from_db()
    assert ag_amanha.status == Agendamento.Status.CANCELADO
    assert ag_amanha.cancelado_por == ag_amanha.colaborador


def test_lembrete_respeita_prazo_de_cancelamento(client, colaborador, massoterapeuta, em):
    inicio = timezone.now() + timedelta(minutes=10)
    ag = Agendamento.objects.create(
        colaborador=colaborador,
        massoterapeuta=massoterapeuta,
        inicio=inicio,
        fim=inicio + timedelta(minutes=20),
        status=Agendamento.Status.CONFIRMADO,
    )
    resposta = client.post(
        reverse("notificacoes:lembrete", args=[tokens.gerar(ag)]), {"acao": "nao-vou"}, HTTP_ACCEPT="application/json"
    )
    assert resposta.status_code == 409
    assert "15 minutos antes" in resposta.json()["mensagem"]


def test_link_de_lembrete_adulterado(client, db):
    resposta = client.get(reverse("notificacoes:lembrete", args=["token-falso"]))
    assert resposta.status_code == 410
    verificar_acessibilidade(resposta.content.decode())


# Inscrição do aparelho
def _inscricao_json(endpoint="https://fcm.googleapis.com/fcm/send/abc"):
    return json.dumps({"endpoint": endpoint, "keys": {"p256dh": "chave", "auth": "segredo"}})


def test_inscrever_e_remover_aparelho(client, colaborador):
    entrar(client, colaborador)
    url = reverse("notificacoes:inscrever")
    assert client.post(url, _inscricao_json(), content_type="application/json").status_code == 201
    assert client.post(url, _inscricao_json(), content_type="application/json").status_code == 201  # idempotente
    assert InscricaoPush.objects.filter(usuario=colaborador).count() == 1

    client.post(
        reverse("notificacoes:remover"),
        json.dumps({"endpoint": "https://fcm.googleapis.com/fcm/send/abc"}),
        content_type="application/json",
    )
    assert not InscricaoPush.objects.exists()


def test_inscricao_invalida_ou_sem_login(client, colaborador):
    url = reverse("notificacoes:inscrever")
    assert client.post(url, _inscricao_json(), content_type="application/json").status_code == 302
    entrar(client, colaborador)
    assert client.post(url, _inscricao_json("http://inseguro"), content_type="application/json").status_code == 400
    assert client.post(url, "não é json", content_type="application/json").status_code == 400


def test_notificacao_de_teste(client, colaborador, enviados):
    inscrever(colaborador)
    entrar(client, colaborador)
    resposta = client.post(reverse("notificacoes:teste"))
    assert resposta.json()["ok"] is True
    assert enviados[0]["dados"]["titulo"] == "Notificação de teste"


# PWA
def test_service_worker_na_raiz(client, db):
    resposta = client.get("/sw.js")
    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("application/javascript")
    assert resposta["Service-Worker-Allowed"] == "/"
    assert "showNotification" in resposta.content.decode()


def test_pagina_offline_acessivel_e_sem_dados_pessoais(client, colaborador):
    entrar(client, colaborador)
    html = client.get(reverse("notificacoes:offline")).content.decode()
    verificar_acessibilidade(html)
    assert colaborador.email not in html and "Ana" not in html


def test_painel_de_notificacoes_nas_preferencias(client, colaborador, settings):
    settings.VAPID_PUBLIC_KEY = "chave-publica"
    entrar(client, colaborador)
    html = client.get(reverse("contas:preferencias")).content.decode()
    assert 'data-chave-publica="chave-publica"' in html
    verificar_acessibilidade(html)
