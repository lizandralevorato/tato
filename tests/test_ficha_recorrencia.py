"""Etapa (d): recorrência de regiões, sugestão para a ficha e convite."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos as agenda
from apps.agenda.models import Agendamento, PoliticaBeneficio
from apps.ficha import servicos
from apps.ficha.models import ConviteFicha, FichaSaude, SugestaoDispensada

from .test_telas import entrar, verificar_acessibilidade

Status = Agendamento.Status


@pytest.fixture
def criar(colaborador, massoterapeuta):
    contador = {"n": 0}

    def _criar(dias_atras, foco=(), observacao="", status=Status.REALIZADO, usuario=None):
        contador["n"] += 1
        inicio = timezone.now().replace(microsecond=0) - timedelta(days=dias_atras, minutes=contador["n"] * 25)
        return Agendamento.objects.create(
            colaborador=usuario or colaborador, massoterapeuta=massoterapeuta, inicio=inicio,
            fim=inicio + timedelta(minutes=20), status=status, foco_regioes=list(foco), observacao=observacao,
        )

    return _criar


# Contagem


def test_tres_vezes_o_mesmo_foco_na_janela_vira_regiao_recorrente(colaborador, criar):
    for dias in (2, 10, 20):
        criar(dias, ["ombros"])
    [r] = servicos.recorrencias(colaborador)
    assert (r.regiao, r.vezes, r.janela_dias, r.apenas_texto) == ("ombros", 3, 30, False)
    assert r.texto == "Região recorrente: ombros (3x em 30 dias)"


def test_abaixo_do_limite_nao_marca(colaborador, criar):
    criar(2, ["ombros"])
    criar(5, ["ombros"])
    assert servicos.recorrencias(colaborador) == []


def test_fora_da_janela_nao_conta(colaborador, criar):
    criar(2, ["ombros"])
    criar(10, ["ombros"])
    criar(45, ["ombros"])
    assert servicos.recorrencias(colaborador) == []


def test_so_contam_realizados_e_marcados(colaborador, criar):
    criar(1, ["ombros"], status=Status.CANCELADO)
    criar(2, ["ombros"], status=Status.EXPIRADO)
    criar(3, ["ombros"], status=Status.FALTA)
    criar(4, ["ombros"], status=Status.REALIZADO)
    criar(5, ["ombros"], status=Status.AGENDADO)
    assert servicos.recorrencias(colaborador) == []
    criar(6, ["ombros"], status=Status.CONFIRMADO)
    assert [r.regiao for r in servicos.recorrencias(colaborador)] == ["ombros"]


def test_agendamento_futuro_marcado_conta(colaborador, criar):
    criar(2, ["ombros"])
    criar(4, ["ombros"])
    criar(-3, ["ombros"], status=Status.AGENDADO)
    assert [r.vezes for r in servicos.recorrencias(colaborador)] == [3]


def test_cada_pessoa_conta_so_os_proprios_pedidos(colaborador, colaborador2, criar):
    for dias in (1, 2, 3):
        criar(dias, ["ombros"], usuario=colaborador2)
    assert servicos.recorrencias(colaborador) == []
    assert len(servicos.recorrencias(colaborador2)) == 1


def test_janela_e_limite_sao_da_unidade(colaborador, unidade, criar):
    for dias in (2, 10, 20):
        criar(dias, ["lombar"])
    politica = PoliticaBeneficio.objects.get(unidade=unidade)
    politica.recorrencia_limite = 4
    politica.save()
    assert servicos.recorrencias(colaborador) == []
    politica.recorrencia_limite, politica.recorrencia_janela_dias = 3, 15
    politica.save()
    assert servicos.recorrencias(colaborador) == []  # só 2 dentro de 15 dias
    politica.recorrencia_janela_dias = 21
    politica.save()
    assert servicos.recorrencias(colaborador)[0].janela_dias == 21


def test_limite_zero_desliga(colaborador, unidade, criar):
    for dias in (1, 2, 3):
        criar(dias, ["ombros"])
    PoliticaBeneficio.objects.filter(unidade=unidade).update(recorrencia_limite=0)
    assert servicos.recorrencias(colaborador) == []


def test_texto_livre_so_apoia_nunca_marca_sozinho(colaborador, criar):
    for dias in (1, 2, 3):
        criar(dias, [], observacao="Hoje o OMBRO está pior")
    [r] = servicos.recorrencias(colaborador)
    assert r.apenas_texto and r.regiao == "ombros"
    assert r.texto.startswith("Região também mencionada no texto")
    # E nunca gera sugestão para a pessoa: só o campo estruturado conta.
    assert servicos.sugestoes_para(colaborador) == []


def test_texto_soma_com_o_estruturado_sem_contar_duas_vezes_o_mesmo_agendamento(colaborador, criar):
    criar(1, ["ombros"], observacao="ombros de novo")  # conta 1, não 2
    criar(2, ["ombros"])
    criar(3, [], observacao="dor no ombro")
    [r] = servicos.recorrencias(colaborador)
    assert r.vezes == 3 and r.apenas_texto


def test_sinonimos_sem_acento_e_sem_diferenciar_maiusculas(colaborador, criar):
    for dias in (1, 2, 3):
        criar(dias, [], observacao="PESCOÇO travado")
    assert servicos.recorrencias(colaborador)[0].regiao == "pescoco"


def test_estruturado_vem_antes_do_texto(colaborador, criar):
    for dias in (1, 2, 3):
        criar(dias, ["joelhos"], observacao="lombar")
    regioes = [(r.regiao, r.apenas_texto) for r in servicos.recorrencias(colaborador)]
    assert regioes == [("joelhos", False), ("lombar", True)]


# Sugestão


def _tres(criar, regiao="ombros"):
    for dias in (1, 2, 3):
        criar(dias, [regiao])


def test_sugere_a_regiao_recorrente(colaborador, criar):
    _tres(criar)
    assert servicos.sugestoes_para(colaborador) == ["ombros"]
    [s] = servicos.sugestoes_para_tela(colaborador)
    assert s["com_artigo"] == "nos ombros"


def test_nao_sugere_o_que_ja_esta_na_ficha(colaborador, criar):
    _tres(criar)
    servicos.salvar_ficha(colaborador, {"regioes": {"ombros": {}}}, True)
    assert servicos.sugestoes_para(colaborador) == []


def test_agora_nao_silencia_por_30_dias(colaborador, criar):
    _tres(criar)
    agora = timezone.now()
    servicos.dispensar_sugestao(colaborador, "ombros", agora)
    assert servicos.sugestoes_para(colaborador, agora + timedelta(days=29)) == []
    # Depois dos 30 dias a janela de contagem andou: refazemos os pedidos para continuar recorrente.
    depois = agora + timedelta(days=31)
    for i, a in enumerate(Agendamento.objects.all()):
        Agendamento.objects.filter(pk=a.pk).update(inicio=depois - timedelta(days=i + 1))
    assert servicos.sugestoes_para(colaborador, depois) == ["ombros"]


def test_agora_nao_de_uma_regiao_nao_cala_as_outras(colaborador, criar):
    _tres(criar, "ombros")
    _tres(criar, "lombar")
    servicos.dispensar_sugestao(colaborador, "ombros")
    assert servicos.sugestoes_para(colaborador) == ["lombar"]


def test_tela_de_confirmacao_mostra_a_sugestao_com_os_dois_botoes(client, colaborador, massoterapeuta, criar, em, unidade):
    PoliticaBeneficio.objects.filter(unidade=unidade).update(max_por_semana=10)
    _tres(criar)
    entrar(client, colaborador)
    inicio = em(timezone.localdate() + timedelta(days=1), 8)
    resposta = client.get(reverse("agenda:agendar_confirmar"), {"inicio": inicio.isoformat(), "m": massoterapeuta.pk})
    html = resposta.content.decode()
    assert "Você tem pedido foco nos ombros com frequência. Quer adicionar na sua ficha?" in html
    assert "Atualizar minha ficha" in html and "Agora não" in html
    assert "não é um diagnóstico" in html
    assert "adicionar=ombros" in html
    verificar_acessibilidade(html)


def test_sugestao_nunca_altera_a_ficha_sozinha(client, colaborador, massoterapeuta, criar, em, unidade):
    PoliticaBeneficio.objects.filter(unidade=unidade).update(max_por_semana=10)
    _tres(criar)
    servicos.salvar_ficha(colaborador, {"regioes": {"pescoco": {}}}, True)
    entrar(client, colaborador)
    inicio = em(timezone.localdate() + timedelta(days=1), 8)
    client.get(reverse("agenda:agendar_confirmar"), {"inicio": inicio.isoformat(), "m": massoterapeuta.pk})
    client.get(reverse("agenda:meus_agendamentos"))
    assert list(FichaSaude.objects.get().regioes.values_list("regiao", flat=True)) == ["pescoco"]


def test_botao_agora_nao_registra_e_some_a_sugestao(client, colaborador, criar):
    _tres(criar)
    entrar(client, colaborador)
    assert "Quer adicionar na sua ficha?" in client.get(reverse("agenda:meus_agendamentos")).content.decode()
    resposta = client.post(reverse("ficha:dispensar"), {"regiao": "ombros", "proximo": reverse("agenda:meus_agendamentos")}, follow=True)
    html = resposta.content.decode()
    assert "Sua ficha não mudou" in html and "Quer adicionar na sua ficha?" not in html
    assert SugestaoDispensada.objects.filter(colaborador=colaborador, regiao="ombros").exists()


def test_dispensar_regiao_inexistente_da_404(client, colaborador):
    entrar(client, colaborador)
    assert client.post(reverse("ficha:dispensar"), {"regiao": "coracao"}).status_code == 404
    assert client.get(reverse("ficha:dispensar")).status_code == 405


# Convite


def test_convite_aparece_na_primeira_vez_e_nao_bloqueia(client, colaborador, massoterapeuta):
    entrar(client, colaborador)
    resposta = client.get(reverse("agenda:agendar_dia"))
    html = resposta.content.decode()
    assert "Quer preencher sua ficha para o massoterapeuta se preparar?" in html
    assert "Preencher agora" in html and "Agora não" in html
    verificar_acessibilidade(html)
    # Não insiste: na segunda visita não aparece.
    assert "Quer preencher sua ficha" not in client.get(reverse("agenda:agendar_dia")).content.decode()
    # E a reserva segue livre.
    assert client.get(reverse("agenda:agendar_dia")).status_code == 200


def test_convite_nao_aparece_para_quem_ja_tem_ficha(client, colaborador, massoterapeuta):
    servicos.salvar_ficha(colaborador, {}, True)
    entrar(client, colaborador)
    assert "Quer preencher sua ficha" not in client.get(reverse("agenda:agendar_dia")).content.decode()


def test_agora_nao_do_convite_confirma_e_volta(client, colaborador, massoterapeuta):
    entrar(client, colaborador)
    client.get(reverse("agenda:agendar_dia"))
    resposta = client.post(reverse("ficha:agora_nao"), follow=True)
    assert "quando quiser" in resposta.content.decode() and resposta.redirect_chain[-1][0] == reverse("agenda:agendar_dia")


def test_lembrete_de_ficha_desatualizada_so_uma_vez_por_periodo(colaborador):
    servicos.salvar_ficha(colaborador, {}, True)
    agora = timezone.now()
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=89)) is None
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=91)) == "desatualizada"
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=95)) is None
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=182)) == "desatualizada"


def test_lembrete_configuravel_e_zero_desliga(colaborador, unidade):
    servicos.salvar_ficha(colaborador, {}, True)
    agora = timezone.now()
    PoliticaBeneficio.objects.filter(unidade=unidade).update(ficha_desatualizada_dias=30)
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=31)) == "desatualizada"
    PoliticaBeneficio.objects.filter(unidade=unidade).update(ficha_desatualizada_dias=0)
    assert servicos.convite_a_mostrar(colaborador, agora + timedelta(days=400)) is None


def test_massoterapeuta_nunca_recebe_convite(massoterapeuta):
    assert servicos.convite_a_mostrar(massoterapeuta.usuario) is None
    assert not ConviteFicha.objects.filter(usuario=massoterapeuta.usuario).exists()


def test_regras_mostra_os_novos_campos_e_salva(client, administrador, unidade):
    entrar(client, administrador)
    html = client.get(reverse("agenda:regras")).content.decode()
    for nome in ("recorrencia_janela_dias", "recorrencia_limite", "ficha_desatualizada_dias"):
        assert f'name="{nome}"' in html
    verificar_acessibilidade(html)
    politica = PoliticaBeneficio.objects.get(unidade=unidade)
    dados = {c.name: getattr(politica, c.name) for c in PoliticaBeneficio._meta.fields if c.name not in {"id", "unidade"}}
    dados.update(recorrencia_janela_dias=45, recorrencia_limite=5, ficha_desatualizada_dias=0)
    dados = {k: ("on" if v is True else v) for k, v in dados.items() if v is not False}
    assert client.post(reverse("agenda:regras"), dados).status_code == 302
    politica.refresh_from_db()
    assert (politica.recorrencia_janela_dias, politica.recorrencia_limite, politica.ficha_desatualizada_dias) == (45, 5, 0)
