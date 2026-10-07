"""Cria dados fictícios para desenvolvimento local.

Uso: python manage.py popular_demo
Todas as contas de demonstração usam a senha definida em SENHA_DEMO.
"""

from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import Disponibilidade, Massoterapeuta, PoliticaBeneficio, Unidade
from apps.comunicados.models import Comunicado
from apps.contas.models import PerfilAcessibilidade, Usuario

SENHA_DEMO = "massagem-demo-2026"
DOMINIO = "demo.local"

MANHA = (time(8, 0), time(11, 40))
TARDE = (time(13, 0), time(16, 40))

MASSOTERAPEUTAS = [
    ("carlos", "Carlos", "Lima", [MANHA, TARDE], {"tema": "ac-escuro", "tamanho_texto": 200, "fala_ativa": True}),
    ("andre", "André", "Souza", [MANHA, TARDE], {"tema": "escuro", "tamanho_texto": 150}),
    ("marcos", "Marcos", "Pereira", [MANHA, TARDE], {"fala_ativa": True, "modo_simplificado": True}),
    ("lucia", "Lúcia", "Ferreira", [MANHA], {"tema": "ac-claro", "tamanho_texto": 250, "fonte": "legivel"}),
]
COLABORADORES = [("ana", "Ana", "Costa"), ("bruno", "Bruno", "Alves"), ("carla", "Carla", "Mendes")]


class Command(BaseCommand):
    help = "Cria unidade, massoterapeutas, colaboradores e agendamentos fictícios."

    @transaction.atomic
    def handle(self, *args, **options):
        unidade, _ = Unidade.objects.get_or_create(nome="Londrina")
        PoliticaBeneficio.objects.get_or_create(unidade=unidade)

        recepcao = self._usuario("recepcao", "Recepção", "Demo", Usuario.Papel.RECEPCAO, unidade)
        recepcao.is_staff = True
        recepcao.is_superuser = True
        recepcao.save()
        self._usuario("gestao", "Gestão", "Demo", Usuario.Papel.GESTAO, unidade)

        massoterapeutas = []
        for apelido, nome, sobrenome, periodos, prefs in MASSOTERAPEUTAS:
            usuario = self._usuario(apelido, nome, sobrenome, Usuario.Papel.MASSOTERAPEUTA, unidade)
            PerfilAcessibilidade.objects.filter(usuario=usuario).update(configurado=True, **prefs)
            m, _ = Massoterapeuta.objects.get_or_create(usuario=usuario, defaults={"unidade": unidade})
            if not m.disponibilidades.exists():
                for dia in range(5):
                    for inicio, fim in periodos:
                        Disponibilidade.objects.create(massoterapeuta=m, dia_semana=dia, hora_inicio=inicio, hora_fim=fim)
            massoterapeutas.append(m)

        colaboradores = [
            self._usuario(apelido, nome, sobrenome, Usuario.Papel.COLABORADOR, unidade)
            for apelido, nome, sobrenome in COLABORADORES
        ]

        criados = self._agendamentos_de_exemplo(unidade, colaboradores)
        Comunicado.objects.get_or_create(
            titulo="Bem-vindos à nova agenda",
            defaults={
                "texto": "A partir de agora, os agendamentos de massagem são feitos por este site. "
                "Vocês recebem aviso no celular quando alguém agenda, chega ou cancela.",
                "autor": recepcao,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Dados de demonstração prontos ({criados} agendamentos novos)."))
        self.stdout.write(f"Contas: <apelido>@{DOMINIO}. Apelidos: recepcao, gestao, "
                          + ", ".join(a for a, *_ in MASSOTERAPEUTAS) + ", "
                          + ", ".join(a for a, *_ in COLABORADORES))
        self.stdout.write("Senha: veja SENHA_DEMO em apps/agenda/management/commands/popular_demo.py")

    def _usuario(self, apelido, nome, sobrenome, papel, unidade):
        usuario, criado = Usuario.objects.get_or_create(
            email=f"{apelido}@{DOMINIO}",
            defaults={"first_name": nome, "last_name": sobrenome, "papel": papel, "unidade": unidade},
        )
        if criado:
            usuario.set_password(SENHA_DEMO)
            usuario.save()
        return usuario

    def _agendamentos_de_exemplo(self, unidade, colaboradores):
        """Um agendamento hoje (ou no próximo dia útil) para cada colaborador."""
        criados = 0
        dia = timezone.localdate()
        for _ in range(7):
            if servicos.horarios_livres(unidade, dia):
                break
            dia += timedelta(days=1)
        livres = servicos.horarios_livres(unidade, dia)
        for colaborador, horario in zip(colaboradores, livres[::3]):
            try:
                servicos.agendar(colaborador, horario.massoterapeuta, horario.inicio)
                criados += 1
            except servicos.RegraViolada:
                pass
        return criados
