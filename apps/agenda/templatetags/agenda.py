from django import template
from django.utils.html import format_html

from .. import formatacao

register = template.Library()

ICONES_STATUS = {
    "agendado": "●",
    "confirmado": "✔",
    "chegou": "➜",
    "expirado": "✖",
    "realizado": "✔",
    "falta": "✖",
    "cancelado": "✖",
}


@register.filter
def hora(valor):
    return formatacao.hora(valor) if valor else ""


@register.filter
def dia(valor):
    return formatacao.dia(valor) if valor else ""


@register.filter
def minutos_ate(valor):
    return formatacao.minutos_ate(valor) if valor else ""


@register.simple_tag
def status(agendamento):
    """Status sempre com ícone + texto (nunca só cor). O ícone é decorativo."""
    return format_html(
        '<span class="status status--{}"><span aria-hidden="true">{}</span> {}</span>',
        agendamento.status,
        ICONES_STATUS.get(agendamento.status, "●"),
        agendamento.get_status_display(),
    )


@register.simple_tag
def widget(campo):
    """Renderiza o input ligando ajuda e erro via aria-describedby e aria-invalid."""
    descritores = []
    if campo.help_text:
        descritores.append(f"{campo.auto_id}-ajuda")
    if campo.errors:
        descritores.append(f"{campo.auto_id}-erro")
    attrs = {}
    if descritores:
        attrs["aria-describedby"] = " ".join(descritores)
    if campo.errors:
        attrs["aria-invalid"] = "true"
    return campo.as_widget(attrs=attrs)
