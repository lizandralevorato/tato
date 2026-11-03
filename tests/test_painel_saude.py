"""Etapa (f): painel de saúde do SESMT e privacidade da ficha."""

import csv
import io
from datetime import timedelta

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Agendamento, PoliticaBeneficio, Unidade
from apps.contas.models import Usuario
from apps.ficha import servicos
from apps.ficha.models import AcessoFicha, FichaSaude

from .conftest import criar_usuario
from .test_telas import entrar, verificar_acessibilidade

PAGINAS = [
    ("painel:saude", []),
    ("painel:saude_fichas", []),
    ("painel:saude_acessos", []),
    ("painel:saude_csv", []),
    ("painel:saude_xlsx", []),
]


@pytest.fixture
def pessoas(unidade):
    return [criar_usuario(f"p{i}@teste.local", Usuario.Papel.COLABORADOR, unidade, f"Pessoa{i}") for i in range(5)]


@pytest.fixture
def fichas(pessoas):
    """5 pessoas: todas com ombros, 3 com lombar, 1 com gestação, 3 com hipertensão."""
    for i, p in enumerate(pessoas):
        regioes = {"ombros": {"intensidade": "forte" if i < 2 else "leve", "frequencia": "sempre" if i == 0 else ""}}
        if i < 3:
            regioes["lombar"] = {}
        condicoes = (["gestacao"] if i == 0 else []) + (["hipertensao"] if i in (1, 2, 3) else [])
        servicos.salvar_ficha(
            p, {"regioes": regioes, "condicoes": condicoes, "evitar": f"segredo-de-{p.first_name}", "autoriza_sesmt": True}, True
        )
    return pessoas


# Permissões


@pytest.mark.parametrize("nome, args", PAGINAS)
def test_so_o_sesmt_entra(client, request, nome, args, fichas):
    url = reverse(nome, args=args)
    for quem in ("administrador", "colaborador", "massoterapeuta"):
        usuario = request.getfixturevalue(quem)
        usuario = getattr(usuario, "usuario", usuario)
        client.logout()
        entrar(client, usuario)
        assert client.get(url).status_code == 403, quem
    client.logout()
    entrar(client, request.getfixturevalue("sesmt"))
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("nome, args", PAGINAS)
def test_superusuario_administrador_nao_entra(client, administrador, nome, args):
    administrador.is_superuser = administrador.is_staff = True
    administrador.save()
    entrar(client, administrador)
    assert client.get(reverse(nome, args=args)).status_code == 403


def test_pagina_de_uma_pessoa_so_para_o_sesmt(client, administrador, colaborador, massoterapeuta, sesmt, fichas):
    url = reverse("painel:saude_pessoa", args=[fichas[0].pk])
    administrador.is_superuser = True
    administrador.save()
    for usuario in (administrador, colaborador, massoterapeuta.usuario, fichas[1]):
        client.logout()
        entrar(client, usuario)
        assert client.get(url).status_code == 403
    client.logout()
    assert client.get(url).status_code == 302  # sem login
    entrar(client, sesmt)
    assert client.get(url).status_code == 200


def test_sesmt_de_outra_unidade_nao_ve_a_pessoa(client, fichas, db):
    outra = Unidade.objects.create(nome="São Paulo")
    PoliticaBeneficio.objects.create(unidade=outra)
    sesmt_sp = criar_usuario("sesmt-sp@teste.local", Usuario.Papel.SESMT, outra, "SesmtSP")
    entrar(client, sesmt_sp)
    assert client.get(reverse("painel:saude_pessoa", args=[fichas[0].pk])).status_code == 404
    html = client.get(reverse("painel:saude")).content.decode()
    assert "0</span> <span class=\"indicador__rotulo\">ficha" in html


def test_fichas_nao_estao_no_admin_do_django():
    from apps.ficha import models

    registrados = {m.__name__ for m in admin.site._registry}
    assert not registrados & {"FichaSaude", "FichaRegiao", "FichaVersao", "AcessoFicha"}
    assert models.FichaSaude not in admin.site._registry


# Painel


def test_painel_de_saude_numeros_e_acessibilidade(client, sesmt, fichas, unidade):
    # Uma ficha antiga: desatualizada.
    FichaSaude.objects.filter(usuario=fichas[4]).update(atualizada_em=timezone.now() - timedelta(days=120))
    entrar(client, sesmt)
    resposta = client.get(reverse("painel:saude"))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    verificar_acessibilidade(html)
    assert "5</span> <span class=\"indicador__rotulo\">fichas preenchidas (de 6 pessoas na unidade)" in html  # 5 + o SESMT
    assert "1</span> <span class=\"indicador__rotulo\">desatualizada" in html
    assert "Regiões mais citadas nas fichas, com o número de pessoas: ombros (5), lombar (3)." in html
    assert "<caption" in html and 'scope="col"' in html and 'scope="row"' in html
    assert "Pressão alta (hipertensão)" in html


def test_ranking_e_condicoes_em_numeros(sesmt, fichas, unidade):
    from apps.ficha import indicadores

    hoje = timezone.localdate()
    dados = indicadores.resumo(unidade, hoje - timedelta(days=30), hoje)
    ranking = {linha["regiao"]: linha for linha in dados["ranking"]}
    assert (ranking["ombros"]["fichas"], ranking["ombros"]["fortes"], ranking["ombros"]["frequentes"]) == (5, 2, 1)
    assert ranking["lombar"]["fichas"] == 3 and ranking["joelhos"]["fichas"] == 0
    assert dados["ranking"][0]["regiao"] == "ombros"
    condicoes = {linha["slug"]: linha["pessoas"] for linha in dados["condicoes"]}
    assert condicoes["hipertensao"] == 3 and condicoes["gestacao"] == 1
    assert dados["preenchidas"] == 5 and dados["desatualizadas"] == 0


def test_focos_do_periodo_entram_no_ranking_e_respeitam_o_periodo(sesmt, fichas, unidade, massoterapeuta):
    from apps.ficha import indicadores

    def marcar(dias, foco, i):
        inicio = timezone.now() - timedelta(days=dias, minutes=30 * i)
        Agendamento.objects.create(
            colaborador=fichas[i], massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
            status=Agendamento.Status.REALIZADO, foco_regioes=foco,
        )

    marcar(2, ["joelhos"], 0)
    marcar(3, ["joelhos", "pes"], 1)
    marcar(40, ["joelhos"], 2)  # fora do período
    hoje = timezone.localdate()
    dados = indicadores.resumo(unidade, hoje - timedelta(days=10), hoje)
    ranking = {linha["regiao"]: linha for linha in dados["ranking"]}
    assert ranking["joelhos"]["focos"] == 2 and ranking["pes"]["focos"] == 1


def test_lista_de_recorrentes_no_painel(client, sesmt, fichas, massoterapeuta, unidade):
    for i in range(3):
        inicio = timezone.now() - timedelta(days=i + 1)
        Agendamento.objects.create(
            colaborador=fichas[0], massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
            status=Agendamento.Status.REALIZADO, foco_regioes=["pescoco"],
        )
    entrar(client, sesmt)
    html = client.get(reverse("painel:saude")).content.decode()
    assert "Região recorrente: pescoço (3x em 30 dias)" in html
    assert reverse("painel:saude_pessoa", args=[fichas[0].pk]) in html


def test_painel_inicio_so_oferece_o_link_ao_sesmt(client, administrador, sesmt, unidade):
    entrar(client, administrador)
    assert "Abrir Saúde e foco" not in client.get(reverse("painel:inicio")).content.decode()
    client.logout()
    entrar(client, sesmt)
    html = client.get(reverse("painel:inicio")).content.decode()
    assert "Abrir Saúde e foco" in html
    verificar_acessibilidade(html)


# Ficha individual


def test_ficha_individual_com_versoes_e_linha_do_tempo(client, sesmt, colaborador, massoterapeuta):
    servicos.salvar_ficha(colaborador, {"regioes": {"ombros": {"intensidade": "forte"}}, "evitar": "mãos geladas", "autoriza_sesmt": True}, True)
    servicos.salvar_ficha(
        colaborador,
        {"regioes": {"ombros": {"intensidade": "leve"}, "pescoco": {}}, "evitar": "mãos geladas", "autoriza_sesmt": True},
        False,
    )
    inicio = timezone.now() - timedelta(days=3)
    Agendamento.objects.create(
        colaborador=colaborador, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
        status=Agendamento.Status.REALIZADO, foco_regioes=["ombros"], observacao="hoje só ombros",
    )
    entrar(client, sesmt)
    resposta = client.get(reverse("painel:saude_pessoa", args=[colaborador.pk]))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Ficha de saúde de Ana" in html and "Evitar: mãos geladas" in html
    assert "Versão 2" in html and "Versão 1" in html and "Ficha criada." in html
    assert "Incluiu região: pescoço." in html
    assert "hoje só ombros" in html and "Linha do tempo de focos" in html
    assert "no-store" in resposta["Cache-Control"]
    verificar_acessibilidade(html)


def test_abrir_ficha_individual_fica_registrado(client, sesmt, colaborador):
    servicos.salvar_ficha(colaborador, {"autoriza_sesmt": True}, True)
    entrar(client, sesmt)
    client.get(reverse("painel:saude_pessoa", args=[colaborador.pk]))
    registro = AcessoFicha.objects.get()
    assert (registro.usuario, registro.colaborador, registro.finalidade) == (sesmt, colaborador, AcessoFicha.Finalidade.SESMT_FICHA)
    # E a própria pessoa vê isso no registro dela.
    client.logout()
    entrar(client, colaborador)
    assert "Sesmt" in client.get(reverse("ficha:meus_acessos")).content.decode()


def test_pessoa_sem_ficha_mostra_so_a_linha_do_tempo(client, sesmt, colaborador):
    entrar(client, sesmt)
    html = client.get(reverse("painel:saude_pessoa", args=[colaborador.pk])).content.decode()
    assert "ainda não preencheu a ficha" in html
    verificar_acessibilidade(html)


def test_massoterapeuta_como_pessoa_da_ficha_da_404(client, sesmt, massoterapeuta):
    entrar(client, sesmt)
    assert client.get(reverse("painel:saude_pessoa", args=[massoterapeuta.usuario.pk])).status_code == 404


def test_lista_de_fichas_busca_por_nome(client, sesmt, fichas):
    entrar(client, sesmt)
    html = client.get(reverse("painel:saude_fichas"), {"q": "pessoa3"}).content.decode()
    assert "Pessoa3" in html and "Pessoa1" not in html
    verificar_acessibilidade(html)


# Registro de acessos


def test_registro_de_acessos_lista_massoterapeuta_e_sesmt(client, sesmt, colaborador, massoterapeuta):
    servicos.registrar_acesso(massoterapeuta.usuario, colaborador, AcessoFicha.Finalidade.ATENDIMENTO)
    servicos.registrar_acesso(sesmt, colaborador, AcessoFicha.Finalidade.SESMT_FICHA)
    entrar(client, sesmt)
    resposta = client.get(reverse("painel:saude_acessos"))
    html = resposta.content.decode()
    assert "Carlos" in html and "Sesmt" in html and "Ana" in html
    assert "Massoterapeuta abriu a ficha do atendimento" in html
    verificar_acessibilidade(html)


# Planilha agregada


def test_csv_agregado_sem_nomes_e_com_grupos_pequenos_escondidos(client, sesmt, fichas):
    entrar(client, sesmt)
    resposta = client.get(reverse("painel:saude_csv"))
    assert resposta.status_code == 200 and resposta["Content-Type"].startswith("text/csv")
    texto = resposta.content.decode("utf-8-sig")
    for p in fichas:
        assert p.first_name not in texto and p.email not in texto
    assert "segredo-de" not in texto
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert linhas[0] == ["Indicador", "Item", "Pessoas"]
    tabela = {(l[0], l[1]): l[2] for l in linhas[1:]}
    assert tabela[("Região com dor (fichas)", "Ombros")] == "5"
    assert tabela[("Região com dor (fichas)", "Lombar (parte baixa das costas)")] == "3"
    assert tabela[("Região com dor (fichas)", "Joelhos")] == "menos de 3"
    assert tabela[("Condição de saúde", "Gestação (gravidez)")] == "menos de 3"  # 1 pessoa: não aponta ninguém
    assert tabela[("Condição de saúde", "Pressão alta (hipertensão)")] == "3"


def test_baixar_a_planilha_fica_registrado(client, sesmt, fichas):
    entrar(client, sesmt)
    client.get(reverse("painel:saude_csv"))
    registro = AcessoFicha.objects.get()
    assert registro.finalidade == AcessoFicha.Finalidade.SESMT_AGREGADO and registro.colaborador is None


# O administrador e as outras planilhas não vazam a ficha


def test_administrador_so_sabe_se_existe_e_se_esta_atualizada(client, administrador, fichas):
    FichaSaude.objects.filter(usuario=fichas[4]).update(atualizada_em=timezone.now() - timedelta(days=200))
    entrar(client, administrador)
    resposta = client.get(reverse("agenda:pessoas"))
    html = resposta.content.decode()
    assert "Ficha atualizada" in html and "Ficha desatualizada" in html and "Sem ficha" in html
    for segredo in ("gestação", "hipertensão", "segredo-de", "ombros", "Ombros"):
        assert segredo not in html
    verificar_acessibilidade(html)


def test_planilhas_existentes_nao_levam_dados_de_saude(client, sesmt, fichas, massoterapeuta):
    inicio = timezone.now() - timedelta(days=1)
    Agendamento.objects.create(
        colaborador=fichas[0], massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
        status=Agendamento.Status.REALIZADO,
    )
    entrar(client, sesmt)
    for nome in ("painel:csv_agendamentos", "painel:csv_resumo"):
        texto = client.get(reverse(nome)).content.decode("utf-8-sig").lower()
        assert "gestação" not in texto and "segredo-de" not in texto and "ombros" not in texto


# Autorização do SESMT


def test_sem_autorizacao_o_sesmt_nao_ve_nome_nem_conteudo(client, sesmt, colaborador):
    servicos.salvar_ficha(colaborador, {"evitar": "segredo-da-ana", "regioes": {"ombros": {}}}, True)
    entrar(client, sesmt)
    html = client.get(reverse("painel:saude_pessoa", args=[colaborador.pk])).content.decode()
    assert "não autorizou" in html and "Ana" not in html.split("<main")[1] and "segredo-da-ana" not in html
    assert not AcessoFicha.objects.exists()
    lista = client.get(reverse("painel:saude_fichas")).content.decode()
    assert "Ana" not in lista.split("<main")[1] and "1 pessoa preencheu a ficha e não autorizou" in lista


def test_planilha_xlsx_leva_nome_so_de_quem_autorizou(client, sesmt, pessoas):
    from openpyxl import load_workbook

    servicos.salvar_ficha(pessoas[0], {"regioes": {"ombros": {"intensidade": "forte"}}, "evitar": "mãos geladas", "autoriza_sesmt": True}, True)
    servicos.salvar_ficha(pessoas[1], {"regioes": {"lombar": {}}, "evitar": "segredo-da-pessoa1"}, True)
    entrar(client, sesmt)
    resposta = client.get(reverse("painel:saude_xlsx"))
    assert resposta.status_code == 200 and "spreadsheetml" in resposta["Content-Type"]
    linhas = list(load_workbook(io.BytesIO(resposta.content)).active.iter_rows(values_only=True))
    cabecalho, dados = linhas[0], linhas[1:]
    assert cabecalho[0] == "Pessoa" and len(dados) == 2
    assert dados[0][0] == "Pessoa0" and "Ombros" in dados[0][3] and dados[0][11] == "mãos geladas"
    assert set(dados[1]) == {"Prefere não dizer", "Não autorizado"}
    assert "Pessoa1" not in str(dados) and "segredo-da-pessoa1" not in str(dados)
    registro = AcessoFicha.objects.get()
    assert registro.finalidade == AcessoFicha.Finalidade.SESMT_PLANILHA and registro.colaborador is None


def test_recorrente_sem_autorizacao_so_entra_na_contagem(sesmt, pessoas, massoterapeuta, unidade):
    from apps.ficha import indicadores

    servicos.salvar_ficha(pessoas[0], {"autoriza_sesmt": True}, True)
    servicos.salvar_ficha(pessoas[1], {}, True)
    for pessoa in pessoas[:2]:
        for i in range(3):
            inicio = timezone.now() - timedelta(days=i + 1)
            Agendamento.objects.create(
                colaborador=pessoa, massoterapeuta=massoterapeuta, inicio=inicio, fim=inicio + timedelta(minutes=20),
                status=Agendamento.Status.REALIZADO, foco_regioes=["pescoco"],
            )
    hoje = timezone.localdate()
    dados = indicadores.resumo(unidade, hoje - timedelta(days=30), hoje)
    assert dados["total_recorrentes"] == 2
    assert [linha["pessoa"] for linha in dados["recorrentes"]] == [pessoas[0]]


def test_retirar_a_autorizacao_esconde_de_novo_e_fica_no_historico(colaborador):
    ficha, _ = servicos.salvar_ficha(colaborador, {"autoriza_sesmt": True}, True)
    assert ficha.autoriza_sesmt
    ficha, versao = servicos.salvar_ficha(colaborador, {}, False)
    assert not ficha.autoriza_sesmt and "Retirou a autorização do SESMT." in versao.mudancas
