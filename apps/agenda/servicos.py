"""Regras de negócio da agenda.

As views só chamam estas funções. Erros de regra viram `RegraViolada` com uma
mensagem em linguagem simples, pronta para mostrar ao usuário.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.contas.models import Usuario
from apps.notificacoes import avisos

from .formatacao import dia as formatar_dia
from .formatacao import hora as formatar_hora
from .formatacao import inicio_da_semana
from .models import (
    Agendamento,
    Bloqueio,
    Disponibilidade,
    HistoricoAgendamento,
    ListaEspera,
    Massoterapeuta,
    PoliticaBeneficio,
    Unidade,
)

Status = Agendamento.Status
Acao = HistoricoAgendamento.Acao


class RegraViolada(Exception):
    """Ação não permitida pelas regras do benefício. A mensagem vai para o usuário."""


class ConflitoDeAgenda(RegraViolada):
    def __init__(self, agendamentos):
        self.agendamentos = agendamentos
        quantos = len(agendamentos)
        super().__init__(
            f"Há {quantos} pessoa{'s' if quantos > 1 else ''} com massagem marcada nesse período. "
            "Confirme se quer cancelar e avisar cada uma."
        )


@dataclass(frozen=True)
class Horario:
    massoterapeuta: Massoterapeuta
    inicio: datetime
    fim: datetime


def _no_fuso(dia: date, hora: time) -> datetime:
    return timezone.make_aware(datetime.combine(dia, hora))


def _limites_do_dia(dia: date):
    inicio = _no_fuso(dia, time.min)
    return inicio, inicio + timedelta(days=1)


def politica_da(unidade: Unidade) -> PoliticaBeneficio:
    politica, _ = PoliticaBeneficio.objects.get_or_create(unidade=unidade)
    return politica


def registrar(agendamento, acao, por=None, detalhe="", agora=None):
    return HistoricoAgendamento.objects.create(
        agendamento=agendamento, acao=acao, por=por, detalhe=detalhe[:300], em=agora or timezone.now()
    )


# Horários livres


def _grade(massoterapeuta, dia: date, periodos=None):
    """Todos os horários da grade semanal do dia, livres ou não."""
    duracao = timedelta(minutes=massoterapeuta.duracao_sessao_min)
    passo = duracao + timedelta(minutes=massoterapeuta.intervalo_min)
    if periodos is None:
        periodos = massoterapeuta.disponibilidades.filter(dia_semana=dia.weekday())
    else:
        periodos = [p for p in periodos if p.dia_semana == dia.weekday()]
    for periodo in periodos:
        inicio = _no_fuso(dia, periodo.hora_inicio)
        limite = _no_fuso(dia, periodo.hora_fim)
        while inicio + duracao <= limite:
            yield inicio, inicio + duracao
            inicio += passo


def _bloqueios_do_dia(massoterapeuta, dia: date):
    inicio_dia, fim_dia = _limites_do_dia(dia)
    return list(
        massoterapeuta.bloqueios.filter(inicio__lt=fim_dia, fim__gt=inicio_dia).values_list("inicio", "fim")
    )


def _ocupados_do_dia(massoterapeuta, dia: date):
    inicio_dia, fim_dia = _limites_do_dia(dia)
    return _bloqueios_do_dia(massoterapeuta, dia) + list(
        massoterapeuta.agendamentos.ativos()
        .filter(inicio__lt=fim_dia, fim__gt=inicio_dia)
        .values_list("inicio", "fim")
    )


def _sobrepoe(inicio, fim, periodos):
    return any(o_ini < fim and o_fim > inicio for o_ini, o_fim in periodos)


def horarios_do_massoterapeuta(massoterapeuta, dia: date, agora=None) -> list[Horario]:
    """Horários livres = disponibilidade semanal menos bloqueios e agendamentos ativos."""
    agora = agora or timezone.now()
    ocupados = _ocupados_do_dia(massoterapeuta, dia)
    return [
        Horario(massoterapeuta, inicio, fim)
        for inicio, fim in _grade(massoterapeuta, dia)
        if inicio > agora and not _sobrepoe(inicio, fim, ocupados)
    ]


def horarios_oferecidos(massoterapeuta, dia: date, periodos=None, bloqueios=None) -> int:
    """Quantos horários o massoterapeuta ofereceu no dia (grade menos folgas e pausas).

    Para muitos dias seguidos, passe `periodos` e `bloqueios` já carregados.
    """
    if bloqueios is None:
        bloqueios = _bloqueios_do_dia(massoterapeuta, dia)
    return sum(
        1 for inicio, fim in _grade(massoterapeuta, dia, periodos) if not _sobrepoe(inicio, fim, bloqueios)
    )


def horarios_livres(unidade, dia: date, massoterapeuta=None, agora=None) -> list[Horario]:
    massoterapeutas = [massoterapeuta] if massoterapeuta else unidade.massoterapeutas.filter(ativo=True)
    horarios = []
    for m in massoterapeutas:
        horarios.extend(horarios_do_massoterapeuta(m, dia, agora))
    return sorted(horarios, key=lambda h: (h.inicio, h.massoterapeuta.nome))


def dias_para_agendar(unidade, colaborador=None, agora=None):
    """Próximos dias de atendimento, com a quantidade de horários livres (0 = lotado)."""
    agora = agora or timezone.now()
    hoje = timezone.localdate(agora)
    politica = politica_da(unidade)
    dias_ocupados = set()
    if colaborador is not None:
        inicio_de_hoje, _ = _limites_do_dia(hoje)
        dias_ocupados = {
            timezone.localtime(inicio).date()
            for inicio in colaborador.agendamentos.ativos()
            .filter(inicio__gte=inicio_de_hoje)
            .values_list("inicio", flat=True)
        }
    dias_de_atendimento = set(
        Disponibilidade.objects.filter(
            massoterapeuta__unidade=unidade, massoterapeuta__ativo=True
        ).values_list("dia_semana", flat=True)
    )
    resultado = []
    for deslocamento in range(politica.dias_para_agendar + 1):
        dia = hoje + timedelta(days=deslocamento)
        livres = len(horarios_livres(unidade, dia, agora=agora))
        if livres or dia in dias_ocupados or (dia.weekday() in dias_de_atendimento and dia > hoje):
            resultado.append({"dia": dia, "livres": livres, "ja_tem_agendamento": dia in dias_ocupados})
    return resultado


# Limites do colaborador


def _status_que_contam(politica):
    status = [Status.AGENDADO, Status.CONFIRMADO, Status.CHEGOU, Status.REALIZADO]
    if politica.falta_conta_no_limite:
        status.append(Status.FALTA)
    return status


def uso_na_semana(colaborador, dia: date, politica) -> int:
    segunda = inicio_da_semana(dia)
    inicio, _ = _limites_do_dia(segunda)
    return colaborador.agendamentos.filter(
        inicio__gte=inicio,
        inicio__lt=inicio + timedelta(days=7),
        status__in=_status_que_contam(politica),
    ).count()


def restantes_na_semana(colaborador, unidade, dia: date | None = None) -> int:
    politica = politica_da(unidade)
    dia = dia or timezone.localdate()
    return max(politica.max_por_semana - uso_na_semana(colaborador, dia, politica), 0)


def _tem_agendamento_no_dia(colaborador, dia: date):
    inicio_dia, fim_dia = _limites_do_dia(dia)
    return colaborador.agendamentos.ativos().filter(inicio__gte=inicio_dia, inicio__lt=fim_dia).exists()


# Agendar


def cabe_encaixe(massoterapeuta, inicio: datetime, agora=None):
    """Encaixe: qualquer hora dentro do expediente, desde que a sessão inteira esteja livre."""
    agora = agora or timezone.now()
    fim = inicio + timedelta(minutes=massoterapeuta.duracao_sessao_min)
    local_ini, local_fim = timezone.localtime(inicio), timezone.localtime(fim)
    dentro = massoterapeuta.disponibilidades.filter(
        dia_semana=local_ini.weekday(), hora_inicio__lte=local_ini.time(), hora_fim__gte=local_fim.time()
    ).exists()
    if not dentro or local_fim.date() != local_ini.date():
        raise RegraViolada(
            f"{formatar_hora(inicio)} fica fora do horário de atendimento de {massoterapeuta.nome} neste dia."
        )
    if _sobrepoe(inicio, fim, _ocupados_do_dia(massoterapeuta, local_ini.date())):
        raise RegraViolada(
            f"{massoterapeuta.nome} já tem atendimento, pausa ou folga entre "
            f"{formatar_hora(inicio)} e {formatar_hora(fim)}."
        )


def validar_agendamento(
    colaborador, massoterapeuta, inicio: datetime, agora=None, encaixe=False, excecao=False, pela_equipe=False
):
    agora = agora or timezone.now()
    politica = politica_da(massoterapeuta.unidade)
    dia = timezone.localtime(inicio).date()
    quem = colaborador.nome if pela_equipe else "Você"

    if colaborador.eh_massoterapeuta or Massoterapeuta.objects.filter(usuario=colaborador).exists():
        raise RegraViolada("Massoterapeutas não podem agendar massagem.")
    if not colaborador.is_active:
        raise RegraViolada(f"O acesso de {colaborador.nome} está desativado.")
    if not massoterapeuta.ativo:
        raise RegraViolada("Este massoterapeuta não está atendendo no momento.")
    if colaborador.unidade_id and colaborador.unidade_id != massoterapeuta.unidade_id:
        raise RegraViolada("Este horário é de outra unidade.")
    if inicio <= agora:
        raise RegraViolada("Esse horário já passou. Escolha outro.")
    if not excecao and dia > timezone.localdate(agora) + timedelta(days=politica.dias_para_agendar):
        raise RegraViolada(
            f"Só é possível agendar com até {politica.dias_para_agendar} dias de antecedência."
        )
    if encaixe:
        cabe_encaixe(massoterapeuta, inicio, agora)
    elif not any(h.inicio == inicio for h in horarios_do_massoterapeuta(massoterapeuta, dia, agora)):
        raise RegraViolada("Esse horário não está mais livre. Escolha outro.")

    if excecao:
        return
    if politica.uma_por_dia and _tem_agendamento_no_dia(colaborador, dia):
        raise RegraViolada(f"{quem} já tem massagem neste dia. A regra permite uma por dia.")
    if uso_na_semana(colaborador, dia, politica) >= politica.max_por_semana:
        raise RegraViolada(
            f"{quem} já usou as {politica.max_por_semana} massagens desta semana "
            "(faltas também contam). Escolha um dia da próxima semana."
        )


def escolher_massoterapeuta(unidade, inicio: datetime, agora=None):
    """Quando o colaborador não tem preferência: quem tem menos atendimentos no dia."""
    dia = timezone.localtime(inicio).date()
    livres = [h.massoterapeuta for h in horarios_livres(unidade, dia, agora=agora) if h.inicio == inicio]
    if not livres:
        raise RegraViolada("Esse horário não está mais livre. Escolha outro.")
    inicio_dia, fim_dia = _limites_do_dia(dia)
    carga = dict(
        Massoterapeuta.objects.filter(pk__in=[m.pk for m in livres])
        .annotate(
            n=Count(
                "agendamentos",
                filter=Q(agendamentos__inicio__gte=inicio_dia, agendamentos__inicio__lt=fim_dia)
                & ~Q(agendamentos__status__in=Agendamento.LIBERAM_HORARIO),
            )
        )
        .values_list("pk", "n")
    )
    return min(livres, key=lambda m: (carga.get(m.pk, 0), m.nome))


def agendar(colaborador, massoterapeuta, inicio: datetime, agora=None, por=None, encaixe=False, excecao=False):
    """Cria o agendamento. `por` é quem agendou, quando não foi a própria pessoa (recepção)."""
    agora = agora or timezone.now()
    pela_equipe = por is not None and por.pk != colaborador.pk
    if encaixe:
        origem, acao = Agendamento.Origem.ENCAIXE, Acao.ENCAIXE
    elif pela_equipe:
        origem, acao = Agendamento.Origem.RECEPCAO, Acao.AGENDADO_EQUIPE
    else:
        origem, acao = Agendamento.Origem.AUTOAGENDAMENTO, Acao.AGENDADO
    with transaction.atomic():
        massoterapeuta = Massoterapeuta.objects.select_for_update().select_related("unidade").get(
            pk=massoterapeuta.pk
        )
        Usuario.objects.select_for_update().filter(pk=colaborador.pk).first()
        validar_agendamento(colaborador, massoterapeuta, inicio, agora, encaixe, excecao, pela_equipe)
        try:
            with transaction.atomic():
                agendamento = Agendamento.objects.create(
                    colaborador=colaborador,
                    massoterapeuta=massoterapeuta,
                    inicio=inicio,
                    fim=inicio + timedelta(minutes=massoterapeuta.duracao_sessao_min),
                    origem=origem,
                )
        except IntegrityError:
            raise RegraViolada("Esse horário acabou de ser reservado por outra pessoa. Escolha outro.")
        registrar(
            agendamento, acao, por or colaborador, "Exceção às regras do benefício." if excecao else "", agora
        )
        # Quem agenda com o check-in já aberto demonstrou agora que vai.
        abre, _, _ = janela_checkin(agendamento)
        if agora >= abre:
            agendamento.status = Status.CONFIRMADO
            agendamento.confirmado_em = agora
            agendamento.save(update_fields=["status", "confirmado_em", "atualizado_em"])
        ListaEspera.objects.filter(
            colaborador=colaborador, dia=timezone.localtime(inicio).date(), ativa=True
        ).update(ativa=False)
        avisos.ao_agendar(agendamento, por if pela_equipe else None)
        return agendamento


# Ações sobre um agendamento


def _politica(agendamento):
    return politica_da(agendamento.massoterapeuta.unidade)


def cancelar(agendamento, por, agora=None):
    agora = agora or timezone.now()
    if agendamento.status not in Agendamento.PENDENTES:
        raise RegraViolada("Este agendamento não pode mais ser cancelado.")
    politica = _politica(agendamento)
    limite = agendamento.inicio - timedelta(minutes=politica.antecedencia_cancelamento_min)
    if not por.eh_equipe and agora > limite:
        raise RegraViolada(
            f"O cancelamento só pode ser feito até {politica.antecedencia_cancelamento_min} minutos "
            f"antes (até {formatar_hora(limite)}). Fale com a recepção."
        )
    with transaction.atomic():
        agendamento.status = Status.CANCELADO
        agendamento.cancelado_em = agora
        agendamento.cancelado_por = por
        agendamento.save(update_fields=["status", "cancelado_em", "cancelado_por", "atualizado_em"])
        registrar(agendamento, Acao.CANCELADO, por, agora=agora)
        avisos.ao_cancelar(agendamento, por)
        avisar_lista_de_espera(agendamento, agora)
    return agendamento


def _cancelar_pelo_massoterapeuta(agendamentos, por, motivo, agora):
    for agendamento in agendamentos:
        agendamento.status = Status.CANCELADO
        agendamento.cancelado_em = agora
        agendamento.cancelado_por = por
        agendamento.save(update_fields=["status", "cancelado_em", "cancelado_por", "atualizado_em"])
        registrar(agendamento, Acao.CANCELADO, por, motivo, agora)
        avisos.ao_cancelar(agendamento, por)


# Check-in (confirmar que vai)


def checkin_obrigatorio(politica):
    return politica.checkin_prazo_min > 0


def janela_checkin(agendamento):
    """(abre, prazo, limite) do check-in.

    O check-in abre em `abre`, deve ser feito até `prazo` e, passado `limite`
    (prazo + tolerância), a reserva é liberada.
    """
    politica = _politica(agendamento)
    if not checkin_obrigatorio(politica):
        return agendamento.inicio - timedelta(minutes=politica.checkin_abre_min), agendamento.inicio, agendamento.inicio
    abre = agendamento.inicio - timedelta(minutes=max(politica.checkin_abre_min, politica.checkin_prazo_min))
    prazo = agendamento.inicio - timedelta(minutes=politica.checkin_prazo_min)
    return abre, prazo, prazo + timedelta(minutes=politica.checkin_tolerancia_min)


def _quando(momento, agora):
    """"às 8h20" se for hoje; "amanhã, quinta-feira, 1 de outubro, às 8h20" se não."""
    if timezone.localtime(momento).date() == timezone.localdate(agora):
        return f"às {formatar_hora(momento)}"
    return f"{formatar_dia(momento, hoje=timezone.localdate(agora))}, às {formatar_hora(momento)}"


def fazer_checkin(agendamento, agora=None, por=None):
    agora = agora or timezone.now()
    if agendamento.status == Status.CONFIRMADO:
        raise RegraViolada("O check-in desta massagem já foi feito.")
    if agendamento.status == Status.EXPIRADO:
        raise RegraViolada(
            "O prazo do check-in terminou e a reserva foi liberada para outra pessoa. "
            "Se ainda houver horário livre, agende de novo."
        )
    if agendamento.status != Status.AGENDADO:
        raise RegraViolada("Não é possível fazer check-in deste agendamento.")
    abre, _, limite = janela_checkin(agendamento)
    if agora < abre:
        raise RegraViolada(f"O check-in abre {_quando(abre, agora)}.")
    if agora > limite:
        raise RegraViolada(f"O prazo do check-in terminou às {formatar_hora(limite)}. Fale com a recepção.")
    # Atualização condicional: se a liberação automática ganhou a corrida, não sobrescreve.
    if not Agendamento.objects.filter(pk=agendamento.pk, status=Status.AGENDADO).update(
        status=Status.CONFIRMADO, confirmado_em=agora, atualizado_em=agora
    ):
        agendamento.refresh_from_db()
        raise RegraViolada("A reserva acabou de ser liberada por falta de check-in.")
    agendamento.status = Status.CONFIRMADO
    agendamento.confirmado_em = agora
    registrar(agendamento, Acao.CHECKIN, por or agendamento.colaborador, agora=agora)
    return agendamento


def liberar_reservas_sem_checkin(agora=None):
    """Libera para outras pessoas as reservas sem check-in depois do prazo + tolerância.

    Roda a cada minuto (comando `notificacoes`) e também antes de listar horários,
    para a vaga aparecer mesmo se o processador estiver parado.
    """
    agora = agora or timezone.now()
    liberadas = []
    for politica in PoliticaBeneficio.objects.all():
        if not checkin_obrigatorio(politica):
            continue
        vencimento = agora + timedelta(minutes=politica.checkin_prazo_min - politica.checkin_tolerancia_min)
        vencidas = Agendamento.objects.filter(
            massoterapeuta__unidade_id=politica.unidade_id,
            status=Status.AGENDADO,
            # No instante exato do limite o check-in ainda vale.
            inicio__lt=vencimento,
            # Horário que já passou fica para o massoterapeuta marcar falta.
            inicio__gt=agora,
        ).select_related("colaborador", "massoterapeuta__usuario", "massoterapeuta__unidade")
        for agendamento in vencidas:
            with transaction.atomic():
                if Agendamento.objects.filter(pk=agendamento.pk, status=Status.AGENDADO).update(
                    status=Status.EXPIRADO, cancelado_em=agora, atualizado_em=agora
                ):
                    agendamento.status = Status.EXPIRADO
                    agendamento.cancelado_em = agora
                    registrar(agendamento, Acao.LIBERADO, agora=agora)
                    avisos.ao_liberar(agendamento)
                    avisar_lista_de_espera(agendamento, agora)
                    liberadas.append(agendamento)
    return liberadas


# Chegada na sala ("Cheguei")


def janela_chegada(agendamento):
    politica = _politica(agendamento)
    return (
        agendamento.inicio - timedelta(minutes=politica.chegada_abre_min),
        agendamento.inicio + timedelta(minutes=politica.tolerancia_min),
    )


def avisar_chegada(agendamento, agora=None):
    agora = agora or timezone.now()
    if agendamento.status not in Agendamento.PENDENTES:
        raise RegraViolada("Não é possível avisar a chegada para este agendamento.")
    abre, fecha = janela_chegada(agendamento)
    if agora < abre:
        raise RegraViolada(f"O aviso de chegada abre às {formatar_hora(abre)}.")
    if agora > fecha:
        raise RegraViolada("A tolerância de atraso já passou. Fale com a recepção.")
    agendamento.status = Status.CHEGOU
    agendamento.chegada_em = agora
    agendamento.save(update_fields=["status", "chegada_em", "atualizado_em"])
    registrar(agendamento, Acao.CHEGADA, agendamento.colaborador, agora=agora)
    avisos.ao_chegar(agendamento)
    return agendamento


def marcar_realizado(agendamento, agora=None, por=None):
    agora = agora or timezone.now()
    if agendamento.status not in Agendamento.EM_ABERTO:
        raise RegraViolada("Este atendimento já foi encerrado.")
    if agora < agendamento.inicio:
        raise RegraViolada(f"Este atendimento só começa às {formatar_hora(agendamento.inicio)}.")
    agendamento.status = Status.REALIZADO
    agendamento.save(update_fields=["status", "atualizado_em"])
    registrar(agendamento, Acao.REALIZADO, por, agora=agora)
    return agendamento


def pode_marcar_falta_a_partir(agendamento):
    return agendamento.inicio + timedelta(minutes=_politica(agendamento).tolerancia_min)


def marcar_falta(agendamento, agora=None, por=None):
    agora = agora or timezone.now()
    if agendamento.status not in Agendamento.PENDENTES:
        raise RegraViolada("Só é possível marcar falta de quem ainda não chegou.")
    a_partir = pode_marcar_falta_a_partir(agendamento)
    if agora < a_partir:
        raise RegraViolada(f"Aguarde a tolerância de atraso. A falta pode ser marcada a partir de {formatar_hora(a_partir)}.")
    agendamento.status = Status.FALTA
    agendamento.save(update_fields=["status", "atualizado_em"])
    registrar(agendamento, Acao.FALTA, por, agora=agora)
    return agendamento


# Massoterapeuta: agenda do dia e pausa


def agenda_do_dia(massoterapeuta, dia: date, incluir_cancelados=False):
    inicio_dia, fim_dia = _limites_do_dia(dia)
    qs = massoterapeuta.agendamentos.filter(inicio__gte=inicio_dia, inicio__lt=fim_dia).select_related("colaborador")
    return qs if incluir_cancelados else qs.ativos()


def proximo_atendimento(massoterapeuta, agora=None):
    agora = agora or timezone.now()
    _, fim_dia = _limites_do_dia(timezone.localdate(agora))
    return (
        massoterapeuta.agendamentos.filter(
            status__in=Agendamento.EM_ABERTO, fim__gte=agora, inicio__lt=fim_dia
        )
        .select_related("colaborador")
        .order_by("inicio")
        .first()
    )


def pausar(massoterapeuta, minutos: int, agora=None):
    """Bloqueia novos agendamentos por alguns minutos. Devolve os atendimentos já marcados no período."""
    agora = agora or timezone.now()
    if minutos not in (5, 10, 15, 30):
        raise RegraViolada("Escolha uma pausa de 5, 10, 15 ou 30 minutos.")
    fim = agora + timedelta(minutes=minutos)
    Bloqueio.objects.create(
        massoterapeuta=massoterapeuta, inicio=agora, fim=fim, motivo=Bloqueio.Motivo.PAUSA
    )
    return list(
        massoterapeuta.agendamentos.filter(
            status__in=Agendamento.EM_ABERTO, inicio__lt=fim, fim__gt=agora
        ).select_related("colaborador")
    )


# Massoterapeuta: horários da semana


def adicionar_periodo(massoterapeuta, dia_semana: int, hora_inicio: time, hora_fim: time):
    if hora_fim <= hora_inicio:
        raise RegraViolada("O horário de término precisa ser depois do horário de início.")
    duracao = timedelta(minutes=massoterapeuta.duracao_sessao_min)
    if datetime.combine(date.min, hora_inicio) + duracao > datetime.combine(date.min, hora_fim):
        raise RegraViolada(f"O período precisa ter pelo menos {massoterapeuta.duracao_sessao_min} minutos, uma sessão.")
    conflito = massoterapeuta.disponibilidades.filter(
        dia_semana=dia_semana, hora_inicio__lt=hora_fim, hora_fim__gt=hora_inicio
    ).first()
    if conflito:
        raise RegraViolada(
            f"Esse período se sobrepõe ao de {formatar_hora(conflito.hora_inicio)} às "
            f"{formatar_hora(conflito.hora_fim)} no mesmo dia. Remova o antigo antes ou escolha outro horário."
        )
    return Disponibilidade.objects.create(
        massoterapeuta=massoterapeuta, dia_semana=dia_semana, hora_inicio=hora_inicio, hora_fim=hora_fim
    )


def agendamentos_no_periodo(periodo, agora=None):
    """Agendamentos futuros que caem nesse período semanal e em nenhum outro que continua."""
    agora = agora or timezone.now()
    outros = list(periodo.massoterapeuta.disponibilidades.exclude(pk=periodo.pk).filter(dia_semana=periodo.dia_semana))
    afetados = []
    for ag in periodo.massoterapeuta.agendamentos.filter(
        status__in=Agendamento.PENDENTES, inicio__gt=agora
    ).select_related("colaborador"):
        ini, fim = timezone.localtime(ag.inicio), timezone.localtime(ag.fim)
        if ini.weekday() != periodo.dia_semana:
            continue
        if not (periodo.hora_inicio <= ini.time() < periodo.hora_fim):
            continue
        if any(o.hora_inicio <= ini.time() and fim.time() <= o.hora_fim for o in outros):
            continue
        afetados.append(ag)
    return afetados


def remover_periodo(periodo, por, cancelar_agendamentos=False, agora=None):
    """Remove um período semanal. Agendamentos já marcados nele continuam, salvo se pedir para cancelar."""
    agora = agora or timezone.now()
    afetados = agendamentos_no_periodo(periodo, agora)
    with transaction.atomic():
        if cancelar_agendamentos:
            _cancelar_pelo_massoterapeuta(afetados, por, "Horário removido da agenda semanal.", agora)
        periodo.delete()
    return afetados


# Massoterapeuta: folgas, férias e ausências


def agendamentos_entre(massoterapeuta, inicio, fim):
    return list(
        massoterapeuta.agendamentos.filter(
            status__in=Agendamento.PENDENTES, inicio__lt=fim, fim__gt=inicio
        ).select_related("colaborador")
    )


def marcar_ausencia(massoterapeuta, inicio, fim, motivo, por, observacao="", cancelar_agendamentos=False, agora=None):
    """Registra folga ou férias. Se houver gente marcada no período, só segue com a confirmação de cancelar."""
    agora = agora or timezone.now()
    if fim <= inicio:
        raise RegraViolada("O fim da ausência precisa ser depois do início.")
    if fim <= agora:
        raise RegraViolada("Esse período já passou.")
    if motivo == Bloqueio.Motivo.PAUSA:
        raise RegraViolada("Para pausas rápidas, use os botões de pausa na tela Minha agenda.")
    conflitos = agendamentos_entre(massoterapeuta, inicio, fim)
    if conflitos and not cancelar_agendamentos:
        raise ConflitoDeAgenda(conflitos)
    with transaction.atomic():
        bloqueio = Bloqueio.objects.create(
            massoterapeuta=massoterapeuta, inicio=inicio, fim=fim, motivo=motivo, observacao=observacao
        )
        detalhe = f"{bloqueio.get_motivo_display()} de {massoterapeuta.nome}."
        _cancelar_pelo_massoterapeuta(conflitos, por, detalhe, agora)
    return bloqueio, conflitos


def remover_ausencia(bloqueio):
    bloqueio.delete()


# Lista de espera


def entrar_na_lista_de_espera(colaborador, unidade, dia: date, massoterapeuta=None, agora=None):
    agora = agora or timezone.now()
    hoje = timezone.localdate(agora)
    politica = politica_da(unidade)
    if colaborador.eh_massoterapeuta:
        raise RegraViolada("Massoterapeutas não podem agendar massagem.")
    if dia < hoje or dia > hoje + timedelta(days=politica.dias_para_agendar):
        raise RegraViolada(
            f"A lista de espera vale para hoje e os próximos {politica.dias_para_agendar} dias."
        )
    if politica.uma_por_dia and _tem_agendamento_no_dia(colaborador, dia):
        raise RegraViolada("Você já tem massagem neste dia.")
    if uso_na_semana(colaborador, dia, politica) >= politica.max_por_semana:
        raise RegraViolada(f"Você já usou as {politica.max_por_semana} massagens da semana desse dia.")
    entrada, _ = ListaEspera.objects.update_or_create(
        colaborador=colaborador,
        dia=dia,
        ativa=True,
        defaults={"unidade": unidade, "massoterapeuta": massoterapeuta},
    )
    return entrada


def sair_da_lista_de_espera(entrada):
    entrada.ativa = False
    entrada.save(update_fields=["ativa"])


def avisar_lista_de_espera(agendamento_liberado, agora=None):
    """Um horário voltou a ficar livre: avisa quem está esperando por esse dia.

    Todos são avisados juntos; quem agendar primeiro fica com o horário.
    """
    agora = agora or timezone.now()
    if agendamento_liberado.inicio <= agora:
        return []
    m = agendamento_liberado.massoterapeuta
    dia = timezone.localtime(agendamento_liberado.inicio).date()
    politica = politica_da(m.unidade)
    avisados = []
    for entrada in (
        ListaEspera.objects.filter(unidade_id=m.unidade_id, dia=dia, ativa=True)
        .filter(Q(massoterapeuta__isnull=True) | Q(massoterapeuta=m))
        .exclude(colaborador_id=agendamento_liberado.colaborador_id)
        .select_related("colaborador")
    ):
        if politica.uma_por_dia and _tem_agendamento_no_dia(entrada.colaborador, dia):
            continue
        if uso_na_semana(entrada.colaborador, dia, politica) >= politica.max_por_semana:
            continue
        avisos.vaga_aberta(entrada, agendamento_liberado)
        entrada.avisado_em = agora
        entrada.save(update_fields=["avisado_em"])
        avisados.append(entrada)
    return avisados


def descrever(agendamento, com_massoterapeuta=True, com_colaborador=False):
    """Frase completa para rótulos e leitores de tela."""
    partes = [f"{formatar_dia(agendamento.inicio)}, às {formatar_hora(agendamento.inicio)}"]
    if com_massoterapeuta:
        partes.append(f"com {agendamento.massoterapeuta.nome}")
    if com_colaborador:
        partes.append(f"com {agendamento.colaborador.nome}")
    return " ".join(partes)
