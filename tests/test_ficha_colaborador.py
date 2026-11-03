"""Etapa (b): ficha de saúde do colaborador (criar, editar, apagar, privacidade)."""

import pytest
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicos as agenda
from apps.ficha import privacidade, servicos
from apps.ficha.models import AcessoFicha, ApagamentoFicha, FichaSaude, FichaVersao

from .test_telas import entrar, verificar_acessibilidade

URL = "ficha:minha"


def dados_validos(**extra):
    dados = {
        "regioes": ["ombros", "lombar"],
        "intensidade_ombros": "forte",
        "frequencia_ombros": "sempre",
        "intensidade_lombar": "leve",
        "condicoes": ["hernia_disco", "gestacao"],
        "condicao_outra": "",
        "dor_cronica": "sim",
        "dor_cronica_descricao": "nas costas",
        "problema_coluna": "nao",
        "pressao": "leve",
        "evitar": "pescoço",
        "observacoes": "",
        "consentimento": "on",
    }
    dados.update(extra)
    return dados


def test_formulario_acessivel_e_com_texto_de_ajuda(client, colaborador):
    entrar(client, colaborador)
    resposta = client.get(reverse(URL))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Preencha só o que quiser. Você pode mudar quando quiser." in html
    assert "Etapa 1 de 3" in html and "Etapa 2 de 3" in html and "Etapa 3 de 3" in html
    assert html.count("<fieldset") >= 5 and "<legend>" in html
    assert privacidade.TEXTO_CONSENTIMENTO in html
    assert "diagnóstico" in html
    verificar_acessibilidade(html)


def test_sem_javascript_todas_as_etapas_e_o_botao_salvar_estao_na_pagina(client, colaborador):
    entrar(client, colaborador)
    html = client.get(reverse(URL)).content.decode()
    # Os controles de etapa começam ocultos; o botão de salvar existe sem depender de JS.
    assert "data-etapas-controles hidden" in html
    assert 'type="submit"' in html and "Salvar minha ficha" in html


def test_pagina_exige_login(client, db):
    resposta = client.get(reverse(URL))
    assert resposta.status_code == 302 and reverse("contas:entrar") in resposta.url


def test_massoterapeuta_nao_tem_ficha(client, massoterapeuta):
    entrar(client, massoterapeuta.usuario)
    assert client.get(reverse(URL)).status_code == 403
    assert client.post(reverse(URL), dados_validos()).status_code == 403


def test_sem_consentimento_nao_salva_e_mostra_o_erro_ligado_ao_campo(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(reverse(URL), dados_validos(consentimento=""))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert not FichaSaude.objects.exists()
    assert 'aria-invalid="true"' in html and 'aria-describedby="id_consentimento-erro"' in html
    assert "resumo-erros" in html
    verificar_acessibilidade(html)


def test_salvar_cria_ficha_regioes_e_primeira_versao(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(reverse(URL), dados_validos())
    assert resposta.status_code == 302 and resposta.url == reverse(URL) + "?salva=1"
    ficha = FichaSaude.objects.get(usuario=colaborador)
    assert ficha.consentimento_versao == privacidade.VERSAO_TEXTO and ficha.consentimento_em
    assert sorted(ficha.condicoes) == ["gestacao", "hernia_disco"]
    ombros = ficha.regioes.get(regiao="ombros")
    assert (ombros.intensidade, ombros.frequencia) == ("forte", "sempre")
    versao = ficha.versoes.get()
    assert versao.numero == 1 and versao.por == colaborador and versao.mudancas == ["Ficha criada."]


def test_depois_de_salvar_o_foco_vai_para_o_titulo_e_a_confirmacao_e_anunciada(client, colaborador):
    entrar(client, colaborador)
    html = client.post(reverse(URL), dados_validos(), follow=True).content.decode()
    assert "Ficha salva" in html
    titulo = html[html.index('<h1 id="titulo-ficha"'):][:200]
    assert "data-focar-ao-carregar" in titulo and "data-anunciar-ao-carregar" in titulo
    # Só um elemento pede o foco inicial: o título (as mensagens não disputam).
    assert html.count("data-focar-ao-carregar") == 1
    assert 'id="anuncio-educado"' in html and 'aria-live="polite"' in html


def test_editar_cria_nova_versao_dizendo_o_que_mudou(client, colaborador):
    entrar(client, colaborador)
    client.post(reverse(URL), dados_validos())
    client.post(
        reverse(URL),
        dados_validos(regioes=["ombros", "joelhos"], intensidade_ombros="leve", condicoes=["hernia_disco"], pressao="firme", consentimento=""),
    )
    ficha = FichaSaude.objects.get(usuario=colaborador)
    assert ficha.versoes.count() == 2
    mudancas = " ".join(ficha.versoes.get(numero=2).mudancas)
    assert "Incluiu região: joelhos" in mudancas
    assert "Tirou região: lombar" in mudancas
    assert "Mudou a região ombros (intensidade leve, frequência sempre)" in mudancas
    assert "Tirou condição: gestação (gravidez)" in mudancas
    assert "preferência de pressão para firme" in mudancas
    # O histórico guarda a foto da versão 1 mesmo depois da edição.
    assert "lombar" in ficha.versoes.get(numero=1).conteudo["regioes"]
    assert "lombar" not in ficha.versoes.get(numero=2).conteudo["regioes"]


def test_editar_nao_pede_o_aceite_de_novo_se_o_texto_nao_mudou(client, colaborador):
    entrar(client, colaborador)
    client.post(reverse(URL), dados_validos())
    html = client.get(reverse(URL)).content.decode()
    assert "Você aceitou o aviso de privacidade em" in html and 'name="consentimento"' not in html
    assert client.post(reverse(URL), dados_validos(consentimento="", evitar="mãos")).status_code == 302


def test_texto_de_privacidade_novo_pede_novo_aceite(client, colaborador):
    entrar(client, colaborador)
    client.post(reverse(URL), dados_validos())
    FichaSaude.objects.update(consentimento_versao="antiga")
    assert 'name="consentimento"' in client.get(reverse(URL)).content.decode()
    assert client.post(reverse(URL), dados_validos(consentimento="")).status_code == 200
    assert client.post(reverse(URL), dados_validos()).status_code == 302
    assert FichaSaude.objects.get().consentimento_versao == privacidade.VERSAO_TEXTO


def test_ficha_vazia_com_aceite_tambem_vale(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(reverse(URL), {"consentimento": "on"})
    assert resposta.status_code == 302
    assert FichaSaude.objects.get(usuario=colaborador).regioes.count() == 0


def test_regiao_invalida_e_rejeitada(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(reverse(URL), dados_validos(regioes=["coracao"]))
    assert resposta.status_code == 200 and not FichaSaude.objects.exists()


def test_regiao_vinda_da_sugestao_chega_marcada_sem_salvar(client, colaborador):
    entrar(client, colaborador)
    html = client.get(reverse(URL), {"adicionar": "ombros", "proximo": "/agendar/"}).content.decode()
    trecho = html[html.index('value="ombros"') - 120 : html.index('value="ombros"') + 40]
    assert "checked" in trecho
    assert 'name="proximo" value="/agendar/"' in html
    assert not FichaSaude.objects.exists()


def test_proximo_volta_para_onde_a_pessoa_estava_e_ignora_endereco_externo(client, colaborador):
    entrar(client, colaborador)
    resposta = client.post(reverse(URL), dados_validos(proximo="/agendar/"))
    assert resposta.url == "/agendar/"
    FichaSaude.objects.all().delete()
    resposta = client.post(reverse(URL), dados_validos(proximo="https://exemplo.com/roubo"))
    assert resposta.url == reverse(URL) + "?salva=1"


def test_confirmacao_para_apagar_e_apagar(client, colaborador):
    entrar(client, colaborador)
    client.post(reverse(URL), dados_validos())
    pagina = client.get(reverse("ficha:apagar"))
    assert pagina.status_code == 200
    verificar_acessibilidade(pagina.content.decode())
    assert FichaSaude.objects.exists()  # GET não apaga

    resposta = client.post(reverse("ficha:apagar"), follow=True)
    assert "foi apagada" in resposta.content.decode()
    assert not FichaSaude.objects.exists() and not FichaVersao.objects.exists()
    registro = ApagamentoFicha.objects.get()
    assert registro.colaborador == colaborador and registro.colaborador_nome == "Ana"


def test_apagar_sem_ficha_da_404(client, colaborador):
    entrar(client, colaborador)
    assert client.get(reverse("ficha:apagar")).status_code == 404


def test_apagar_pode_levar_as_observacoes_das_massagens(client, colaborador, massoterapeuta, em, segunda):
    ag = agenda.agendar(colaborador, massoterapeuta, em(segunda, 8))
    ag.foco_regioes, ag.observacao = ["ombros"], "ombros hoje"
    ag.save()
    entrar(client, colaborador)
    client.post(reverse(URL), dados_validos())
    client.post(reverse("ficha:apagar"))  # sem marcar: observações ficam
    ag.refresh_from_db()
    assert ag.foco_regioes == ["ombros"]
    client.post(reverse(URL), dados_validos())
    client.post(reverse("ficha:apagar"), {"apagar_observacoes": "on"})
    ag.refresh_from_db()
    assert ag.foco_regioes == [] and ag.observacao == ""


def test_colaborador_ve_quem_abriu_a_ficha(client, colaborador, massoterapeuta):
    servicos.registrar_acesso(massoterapeuta.usuario, colaborador, AcessoFicha.Finalidade.ATENDIMENTO)
    servicos.registrar_acesso(massoterapeuta.usuario, None, AcessoFicha.Finalidade.SESMT_AGREGADO)
    entrar(client, colaborador)
    resposta = client.get(reverse("ficha:meus_acessos"))
    html = resposta.content.decode()
    assert "Carlos" in html and "Massoterapeuta abriu a ficha do atendimento" in html
    assert "planilha agregada" not in html
    verificar_acessibilidade(html)


def test_cada_um_ve_so_os_proprios_acessos(client, colaborador, colaborador2, massoterapeuta):
    servicos.registrar_acesso(massoterapeuta.usuario, colaborador, AcessoFicha.Finalidade.ATENDIMENTO)
    entrar(client, colaborador2)
    assert "Ninguém abriu a sua ficha" in client.get(reverse("ficha:meus_acessos")).content.decode()


def test_pagina_de_privacidade_e_publica_e_acessivel(client, db):
    resposta = client.get(reverse("ficha:privacidade"))
    html = resposta.content.decode()
    assert resposta.status_code == 200
    for titulo, _ in privacidade.AVISO:
        assert titulo in html
    verificar_acessibilidade(html)


@pytest.mark.parametrize("quem", ["administrador", "sesmt"])
def test_administrador_e_sesmt_tambem_tem_a_propria_ficha(client, request, quem):
    usuario = request.getfixturevalue(quem)
    entrar(client, usuario)
    assert client.post(reverse(URL), dados_validos()).status_code == 302
    assert FichaSaude.objects.get().usuario == usuario


def test_menu_do_colaborador_tem_o_link_da_ficha(client, colaborador):
    entrar(client, colaborador)
    html = client.get(reverse("agenda:meus_agendamentos")).content.decode()
    assert reverse(URL) in html and "Minha ficha de saúde" in html


def test_situacao_da_ficha_nao_expoe_conteudo(colaborador, unidade):
    assert servicos.situacao_da_ficha(colaborador)["existe"] is False
    servicos.salvar_ficha(colaborador, {"condicoes": ["gestacao"], "evitar": "segredo"}, True)
    situacao = servicos.situacao_da_ficha(colaborador)
    assert situacao["existe"] and not situacao["desatualizada"]
    assert "gestação" not in situacao["texto"].lower() and "segredo" not in situacao["texto"]
    depois = timezone.now() + timedelta(days=91)
    assert servicos.situacao_da_ficha(colaborador, depois)["desatualizada"] is True


def test_autorizacao_do_sesmt_e_opcional_e_pode_ser_retirada(client, colaborador):
    entrar(client, colaborador)
    assert 'name="autoriza_sesmt"' in client.get(reverse(URL)).content.decode()
    assert client.post(reverse(URL), dados_validos()).status_code == 302
    assert FichaSaude.objects.get().autoriza_sesmt is False
    assert client.post(reverse(URL), dados_validos(autoriza_sesmt="on", consentimento="")).status_code == 302
    assert FichaSaude.objects.get().autoriza_sesmt is True
    assert client.post(reverse(URL), dados_validos(consentimento="")).status_code == 302
    assert FichaSaude.objects.get().autoriza_sesmt is False
