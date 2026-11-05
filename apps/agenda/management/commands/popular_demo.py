"""Cria dados fictícios para desenvolvimento local.

Uso: python manage.py popular_demo
     python manage.py popular_demo --agora   (também cria um atendimento da Ana com o Carlos
                                              começando daqui a 30 minutos, para testar "Ver ficha")
Todas as contas de demonstração usam a senha definida em SENHA_DEMO.
"""

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.agenda import servicos
from apps.agenda.models import Agendamento, Disponibilidade, Massoterapeuta, PoliticaBeneficio, Unidade
from apps.comunicados.models import Comunicado
from apps.contas.models import PerfilAcessibilidade, Usuario
from apps.ficha import servicos as ficha
from apps.ficha.models import FichaSaude

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

# Fichas fictícias. A Carla fica sem ficha, para mostrar "Sem ficha preenchida".
FICHAS_DEMO = {
    "ana": {
        "regioes": {
            "ombros": {"intensidade": "forte", "frequencia": "frequente"},
            "lombar": {"intensidade": "moderada", "frequencia": "as_vezes"},
        },
        "condicoes": ["hernia_disco", "anticoagulante"],
        "dor_cronica": True,
        "dor_cronica_descricao": "Dor nas costas há dois anos.",
        "pressao": "leve",
        "evitar": "Não apertar a lombar.",
        "observacoes": "Trabalho muito tempo sentada.",
        "autoriza_sesmt": True,
    },
    "bruno": {
        "regioes": {"pescoco": {"intensidade": "leve", "frequencia": "as_vezes"}},
        "condicoes": ["enxaqueca"],
        "pressao": "firme",
    },
}
# Caso de demonstração de região recorrente: a Ana pediu foco nos ombros 3 vezes nos últimos 30 dias.
RECORRENTE_DEMO = ("ana", "ombros", [8, 15, 22])


class Command(BaseCommand):
    help = "Cria unidade, massoterapeutas, colaboradores, fichas e agendamentos fictícios."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sem-reservas",
            action="store_true",
            help="Não cria agendamentos de exemplo (agenda livre).",
        )
        parser.add_argument(
            "--agora",
            action="store_true",
            help="Cria um atendimento da Ana com o Carlos daqui a 30 minutos (para testar o botão Ver ficha).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        unidade, _ = Unidade.objects.get_or_create(nome="Londrina")
        PoliticaBeneficio.objects.get_or_create(unidade=unidade)

        administrador = self._usuario("administrador", "Administrador", "Demo", Usuario.Papel.ADMINISTRADOR, unidade)
        administrador.is_staff = True
        administrador.is_superuser = True
        administrador.save()
        self._usuario("sesmt", "SESMT", "Demo", Usuario.Papel.SESMT, unidade)

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

        fichas = self._fichas(colaboradores)
        if options["sem_reservas"]:
            recorrentes = criados = 0
        else:
            recorrentes = self._regiao_recorrente(colaboradores, massoterapeutas[0])
            criados = self._agendamentos_de_exemplo(unidade, colaboradores)
        if options["agora"]:
            self._atendimento_agora(colaboradores[0], massoterapeutas[0])
        Comunicado.objects.get_or_create(
            titulo="Bem-vindos à nova agenda",
            defaults={
                "texto": "A partir de agora, os agendamentos de massagem são feitos por este site. "
                "Vocês recebem aviso no celular quando alguém agenda, chega ou cancela.",
                "autor": administrador,
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Dados de demonstração prontos ({criados} agendamentos novos)."))
        self.stdout.write(f"Fichas de saúde fictícias novas: {fichas}. Pedidos de foco de demonstração novos: {recorrentes}.")
        self.stdout.write(f"Contas: <apelido>@{DOMINIO}. Apelidos: administrador, sesmt, "
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

    def _fichas(self, colaboradores):
        """Fichas fictícias (só para quem ainda não tem uma)."""
        criadas = 0
        for usuario in colaboradores:
            dados = FICHAS_DEMO.get(usuario.email.split("@")[0])
            if dados and not FichaSaude.objects.filter(usuario=usuario).exists():
                ficha.salvar_ficha(usuario, dados, consentimento=True)
                criadas += 1
        return criadas

    def _regiao_recorrente(self, colaboradores, massoterapeuta):
        """Pedidos de foco antigos, para o painel do SESMT e a agenda mostrarem uma região recorrente."""
        apelido, regiao, dias_atras = RECORRENTE_DEMO
        usuario = next(c for c in colaboradores if c.email.startswith(f"{apelido}@"))
        criados = 0
        for dias in dias_atras:
            dia = timezone.localdate() - timedelta(days=dias)
            while dia.weekday() > 4:  # sem fim de semana
                dia -= timedelta(days=1)
            inicio = timezone.make_aware(datetime.combine(dia, time(10, 0)))
            _, novo = Agendamento.objects.get_or_create(
                colaborador=usuario,
                massoterapeuta=massoterapeuta,
                inicio=inicio,
                defaults={
                    "fim": inicio + timedelta(minutes=massoterapeuta.duracao_sessao_min),
                    "status": Agendamento.Status.REALIZADO,
                    "foco_regioes": [regiao],
                    "observacao": "Hoje quero focar nos ombros." if dias == dias_atras[0] else "",
                    "observacao_em": inicio - timedelta(days=1),
                },
            )
            criados += novo
        return criados

    def _atendimento_agora(self, colaborador, massoterapeuta):
        inicio = (timezone.now() + timedelta(minutes=30)).replace(second=0, microsecond=0)
        if timezone.localtime(inicio).date() != timezone.localdate():
            self.stdout.write(self.style.WARNING("Já é tarde: o atendimento de agora cairia amanhã e não apareceria na agenda de hoje."))
            return
        _, novo = Agendamento.objects.get_or_create(
            massoterapeuta=massoterapeuta,
            inicio=inicio,
            defaults={
                "colaborador": colaborador,
                "fim": inicio + timedelta(minutes=massoterapeuta.duracao_sessao_min),
                "status": Agendamento.Status.CONFIRMADO,
                "confirmado_em": timezone.now(),
                "foco_regioes": ["ombros"],
                "observacao": "Já fiz massagem esta semana, hoje quero focar nos ombros.",
                "observacao_em": timezone.now(),
            },
        )
        if novo:
            self.stdout.write(f"Atendimento de teste: Ana com {massoterapeuta.nome} às {timezone.localtime(inicio):%H:%M}.")

    def _agendamentos_de_exemplo(self, unidade, colaboradores):
        """Um agendamento hoje (ou no próximo dia útil) para cada colaborador."""
        criados = 0
        dia = timezone.localdate()
        for _ in range(7):
            if servicos.horarios_livres(unidade, dia):
                break
            dia += timedelta(days=1)
        livres = servicos.horarios_livres(unidade, dia)
        pedidos = [
            (["ombros"], "Já fiz massagem esta semana, hoje quero focar nos ombros."),
            (["pescoco", "costas_altas"], ""),
            ([], ""),
        ]
        for colaborador, horario, (foco, observacao) in zip(colaboradores, livres[::3], pedidos):
            try:
                servicos.agendar(
                    colaborador, horario.massoterapeuta, horario.inicio, foco_regioes=foco, observacao=observacao
                )
                criados += 1
            except servicos.RegraViolada:
                pass
        return criados
