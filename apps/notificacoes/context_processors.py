from django.conf import settings


def push(request):
    return {"vapid_chave_publica": settings.VAPID_PUBLIC_KEY}
