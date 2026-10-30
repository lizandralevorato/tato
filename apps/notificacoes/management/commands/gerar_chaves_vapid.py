"""Gera o par de chaves VAPID usado pelo Web Push.

Gere uma vez por ambiente e guarde no .env. Trocar as chaves invalida os
aparelhos já inscritos (as pessoas precisam ativar as notificações de novo).
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand


def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


class Command(BaseCommand):
    help = "Gera chaves VAPID para o .env."

    def handle(self, *args, **options):
        chave = ec.generate_private_key(ec.SECP256R1())
        privada = chave.private_numbers().private_value.to_bytes(32, "big")
        publica = chave.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self.stdout.write("# Cole no arquivo .env (não versionar a chave privada):")
        self.stdout.write(f"VAPID_PUBLIC_KEY={_b64url(publica)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={_b64url(privada)}")
        self.stdout.write("VAPID_CONTATO=mailto:administrador@suaempresa.com.br")
