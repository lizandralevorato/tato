from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilAcessibilidade


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def criar_perfil_acessibilidade(sender, instance, created, **kwargs):
    if created:
        PerfilAcessibilidade.objects.get_or_create(usuario=instance)
