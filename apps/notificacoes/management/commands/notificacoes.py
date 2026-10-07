"""Processa lembretes e avisos periódicos.

Desenvolvimento:  python manage.py notificacoes --continuo
Servidor:         agende `python manage.py notificacoes` a cada minuto
                  (Agendador de Tarefas do Windows, cron ou systemd timer).
"""

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notificacoes import push, tarefas


class Command(BaseCommand):
    help = "Libera reservas sem check-in, envia lembretes de check-in e avisos, e reenvia falhas."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true", help="Fica rodando, um ciclo por intervalo.")
        parser.add_argument("--intervalo", type=int, default=60, help="Segundos entre ciclos (padrão 60).")

    def handle(self, *args, continuo=False, intervalo=60, **options):
        if not push.configurado():
            self.stderr.write(
                "Aviso: chaves VAPID não configuradas. Os avisos serão registrados, mas não enviados. "
                "Rode `python manage.py gerar_chaves_vapid`."
            )
        while True:
            try:
                resultado = tarefas.rodar_ciclo()
            except Exception as erro:  # noqa: BLE001 (no modo contínuo, um erro não pode parar os lembretes)
                if not continuo:
                    raise
                self.stderr.write(f"{timezone.localtime():%H:%M:%S} erro no ciclo: {erro}")
            else:
                if any(resultado.values()) or not continuo:
                    resumo = " ".join(f"{chave}={valor}" for chave, valor in resultado.items())
                    self.stdout.write(f"{timezone.localtime():%H:%M:%S} {resumo}")
            if not continuo:
                return
            time.sleep(intervalo)
