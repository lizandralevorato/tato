"""Etapa (a): modelos, vocabulário e migrações da ficha de saúde."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.ficha.models import FichaRegiao, FichaSaude, FichaVersao, VersaoImutavel
from apps.ficha.vocabulario import Regiao, regioes_no_texto


def _ficha(usuario):
    agora = timezone.now()
    return FichaSaude.objects.create(
        usuario=usuario, consentimento_em=agora, consentimento_versao="t", criada_em=agora, atualizada_em=agora
    )


def test_sem_migracao_pendente(db, capsys):
    call_command("makemigrations", "--check", "--dry-run")


@pytest.mark.django_db(transaction=True)
def test_migracoes_sao_reversiveis():
    executor = MigrationExecutor(connection)
    antes = [("agenda", "0007_origem_administrador"), ("contas", "0004_administrador_sesmt")]
    executor.migrate(antes + [("ficha", None)])
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    atual = [n for n in executor.loader.graph.leaf_nodes() if n[0] in {"agenda", "contas", "ficha"}]
    executor.migrate(atual)  # volta ao estado atual para não atrapalhar os outros testes


def test_versao_nao_pode_ser_alterada_nem_apagada(colaborador):
    ficha = _ficha(colaborador)
    versao = FichaVersao.objects.create(ficha=ficha, numero=1, em=timezone.now())
    versao.numero = 2
    with pytest.raises(VersaoImutavel):
        versao.save()
    with pytest.raises(VersaoImutavel):
        versao.delete()
    with pytest.raises(VersaoImutavel):
        FichaVersao.objects.filter(pk=versao.pk).update(numero=3)
    with pytest.raises(VersaoImutavel):
        FichaVersao.objects.filter(pk=versao.pk).delete()


def test_apagar_a_ficha_leva_regioes_e_versoes(colaborador):
    ficha = _ficha(colaborador)
    FichaRegiao.objects.create(ficha=ficha, regiao=Regiao.OMBROS)
    FichaVersao.objects.create(ficha=ficha, numero=1, em=timezone.now())
    ficha.delete()
    assert not FichaRegiao.objects.exists() and not FichaVersao.objects.exists()


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("Hoje quero focar nos OMBROS", ["ombros"]),
        ("dor no pescoço e na lombar", ["pescoco", "lombar"]),
        ("dor nas costas", ["costas_altas"]),
        ("Cabeça pesada", ["cabeca_mandibula"]),
        ("tudo bem hoje", []),
        ("compensei o pé direito", ["pes"]),
        ("trapézio duro", ["ombros"]),
    ],
)
def test_palavras_de_regiao_no_texto(texto, esperado):
    assert sorted(regioes_no_texto(texto)) == sorted(esperado)
