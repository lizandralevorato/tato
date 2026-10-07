import csv
from datetime import date, timedelta

from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlencode

from apps.agenda.formatacao import hora
from apps.agenda.models import HistoricoAgendamento, Unidade
from apps.agenda.views import acesso
from apps.agenda.views.recepcao import unidade_da_equipe

from . import indicadores

MAX_DIAS = 366


def _filtros(request):
    hoje = timezone.localdate()
    try:
        ate = date.fromisoformat(request.GET.get("ate", ""))
    except ValueError:
        ate = hoje
    try:
        de = date.fromisoformat(request.GET.get("de", ""))
    except ValueError:
        de = ate - timedelta(days=29)
    if de > ate:
        de, ate = ate, de
    erro = ""
    if (ate - de).days >= MAX_DIAS:
        de = ate - timedelta(days=MAX_DIAS - 1)
        erro = "O período máximo é de um ano. Mostrando os últimos 366 dias até a data final."
    unidade = unidade_da_equipe(request)
    massoterapeuta = None
    m_id = request.GET.get("m", "")
    if unidade and m_id.isdigit():
        massoterapeuta = unidade.massoterapeutas.filter(pk=m_id).select_related("usuario").first()
    return {"de": de, "ate": ate, "unidade": unidade, "massoterapeuta": massoterapeuta, "erro": erro}


def _consulta(filtros, **extra):
    params = {"de": filtros["de"].isoformat(), "ate": filtros["ate"].isoformat()}
    if filtros["massoterapeuta"]:
        params["m"] = filtros["massoterapeuta"].pk
    if filtros["unidade"]:
        params["unidade"] = filtros["unidade"].pk
    params.update(extra)
    return urlencode(params)


@acesso.equipe
def inicio(request):
    filtros = _filtros(request)
    unidade = filtros["unidade"]
    dados = indicadores.resumo(unidade, filtros["de"], filtros["ate"], filtros["massoterapeuta"]) if unidade else None
    maior_semana = max((linha.reservados for linha in dados["por_semana"]), default=0) if dados else 0
    return render(
        request,
        "painel/inicio.html",
        {
            **filtros,
            "dados": dados,
            "maior_semana": maior_semana or 1,
            "unidades": Unidade.objects.filter(ativa=True) if not request.user.unidade_id else [],
            "massoterapeutas": unidade.massoterapeutas.select_related("usuario") if unidade else [],
            "consulta": _consulta(filtros),
        },
    )


def _csv(nome):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    resposta.write("﻿")  # BOM: o Excel abre os acentos corretamente
    return resposta, csv.writer(resposta, delimiter=";")


@acesso.equipe
def csv_agendamentos(request):
    filtros = _filtros(request)
    resposta, escritor = _csv(f"agendamentos_{filtros['de']}_{filtros['ate']}.csv")
    escritor.writerow(
        ["Data", "Hora", "Massoterapeuta", "Colaborador", "E-mail", "Situação", "Origem", "Agendado em", "Cancelado por"]
    )
    if filtros["unidade"]:
        qs = indicadores.agendamentos(
            filtros["unidade"], filtros["de"], filtros["ate"], filtros["massoterapeuta"]
        ).select_related("colaborador", "massoterapeuta__usuario", "cancelado_por")
        for ag in qs.order_by("inicio"):
            escritor.writerow(
                [
                    timezone.localtime(ag.inicio).strftime("%d/%m/%Y"),
                    hora(ag.inicio),
                    ag.massoterapeuta.nome,
                    ag.colaborador.nome,
                    ag.colaborador.email,
                    ag.get_status_display(),
                    ag.get_origem_display(),
                    timezone.localtime(ag.criado_em).strftime("%d/%m/%Y %H:%M"),
                    ag.cancelado_por.nome if ag.cancelado_por else "",
                ]
            )
    return resposta


@acesso.equipe
def csv_resumo(request):
    filtros = _filtros(request)
    resposta, escritor = _csv(f"resumo_{filtros['de']}_{filtros['ate']}.csv")
    escritor.writerow(
        [
            "Massoterapeuta", "Horários oferecidos", "Reservados", "Ocupação (%)", "Atendidos", "Faltas",
            "Faltas (%)", "Cancelados", "Liberados sem check-in", "Pela recepção ou encaixe",
        ]
    )
    if filtros["unidade"]:
        dados = indicadores.resumo(filtros["unidade"], filtros["de"], filtros["ate"], filtros["massoterapeuta"])
        for linha in [*dados["por_massoterapeuta"], dados["geral"]]:
            escritor.writerow(
                [
                    linha.rotulo, linha.oferecidos, linha.reservados, linha.ocupacao if linha.ocupacao is not None else "",
                    linha.realizados, linha.faltas, linha.taxa_faltas if linha.taxa_faltas is not None else "",
                    linha.cancelados, linha.liberados, linha.encaixes,
                ]
            )
    return resposta


@acesso.equipe
def historico(request):
    filtros = _filtros(request)
    eventos = HistoricoAgendamento.objects.none()
    if filtros["unidade"]:
        inicio, fim = indicadores.limites(filtros["de"], filtros["ate"])
        eventos = (
            HistoricoAgendamento.objects.filter(
                em__gte=inicio, em__lt=fim, agendamento__massoterapeuta__unidade=filtros["unidade"]
            )
            .select_related("por", "agendamento__colaborador", "agendamento__massoterapeuta__usuario")
        )
        if filtros["massoterapeuta"]:
            eventos = eventos.filter(agendamento__massoterapeuta=filtros["massoterapeuta"])
        acao = request.GET.get("acao", "")
        if acao in HistoricoAgendamento.Acao.values:
            eventos = eventos.filter(acao=acao)
    pagina = Paginator(eventos, 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "painel/historico.html",
        {
            **filtros,
            "pagina": pagina,
            "acoes": HistoricoAgendamento.Acao.choices,
            "acao": request.GET.get("acao", ""),
            "unidades": Unidade.objects.filter(ativa=True) if not request.user.unidade_id else [],
            "massoterapeutas": filtros["unidade"].massoterapeutas.select_related("usuario") if filtros["unidade"] else [],
            "consulta": _consulta(filtros, acao=request.GET.get("acao", "")),
        },
    )
