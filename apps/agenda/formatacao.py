"""Formatação de datas e horas para leitura natural (tela e leitor de tela)."""

from datetime import date, datetime, timedelta

from django.utils import timezone
from django.utils.formats import date_format


def hora(valor):
    """9h20, 13h (nunca "09:20:00")."""
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor)
    if valor.minute:
        return f"{valor.hour}h{valor.minute:02d}"
    return f"{valor.hour}h"


def dia(valor, hoje=None):
    """"hoje, terça-feira, 7 de outubro" / "amanhã, ..." / "quinta-feira, 9 de outubro"."""
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor).date()
    hoje = hoje or timezone.localdate()
    texto = date_format(valor, r"l, j \d\e F").lower()
    if valor == hoje:
        return f"hoje, {texto}"
    if valor == hoje + timedelta(days=1):
        return f"amanhã, {texto}"
    return texto


def minutos_ate(inicio, agora=None):
    """"agora", "em 1 minuto", "em 12 minutos", "em 1 hora e 5 minutos"."""
    agora = agora or timezone.now()
    minutos = int((inicio - agora).total_seconds() // 60)
    if minutos <= 0:
        return "agora"
    horas, resto = divmod(minutos, 60)
    partes = []
    if horas:
        partes.append(f"{horas} hora" + ("s" if horas > 1 else ""))
    if resto:
        partes.append(f"{resto} minuto" + ("s" if resto > 1 else ""))
    return "em " + " e ".join(partes)


def inicio_da_semana(valor: date) -> date:
    return valor - timedelta(days=valor.weekday())
