from django.urls import path

from .views import colaborador, massoterapeuta, recepcao

app_name = "agenda"

urlpatterns = [
    # Colaborador
    path("meus-agendamentos/", colaborador.meus_agendamentos, name="meus_agendamentos"),
    path("agendar/", colaborador.agendar_dia, name="agendar_dia"),
    path("agendar/confirmar/", colaborador.agendar_confirmar, name="agendar_confirmar"),
    path("agendar/<str:dia>/", colaborador.agendar_horario, name="agendar_horario"),
    path("agendamentos/<int:pk>/cancelar/", colaborador.cancelar, name="cancelar"),
    path("agendamentos/<int:pk>/check-in/", colaborador.checkin, name="checkin"),
    path("agendamentos/<int:pk>/cheguei/", colaborador.chegada, name="chegada"),
    path("lista-de-espera/entrar/", colaborador.entrar_na_espera, name="entrar_na_espera"),
    path("lista-de-espera/<int:pk>/sair/", colaborador.sair_da_espera, name="sair_da_espera"),
    # Massoterapeuta
    path("massoterapeuta/", massoterapeuta.agora, name="agora"),
    path("massoterapeuta/ao-vivo/", massoterapeuta.agora_parcial, name="agora_parcial"),
    path("massoterapeuta/estado.json", massoterapeuta.estado_json, name="estado_json"),
    path("massoterapeuta/pausa/", massoterapeuta.pausar, name="pausar"),
    path("massoterapeuta/disponibilidade/", massoterapeuta.disponibilidade, name="disponibilidade"),
    path(
        "massoterapeuta/disponibilidade/<int:pk>/remover/", massoterapeuta.remover_periodo, name="remover_periodo"
    ),
    path("massoterapeuta/ausencias/<int:pk>/remover/", massoterapeuta.remover_ausencia, name="remover_ausencia"),
    path("massoterapeuta/agendamentos/<int:pk>/atendido/", massoterapeuta.marcar_atendido, name="atendido"),
    path("massoterapeuta/agendamentos/<int:pk>/faltou/", massoterapeuta.marcar_falta, name="faltou"),
    # Recepção e gestão
    path("recepcao/", recepcao.agenda_da_unidade, name="recepcao"),
    path("recepcao/agendar/", recepcao.agendar_para, name="recepcao_agendar"),
    path("recepcao/agendamentos/<int:pk>/", recepcao.agendamento_detalhe, name="recepcao_agendamento"),
    path(
        "recepcao/agendamentos/<int:pk>/<str:acao>/", recepcao.marcar_pela_equipe, name="recepcao_marcar"
    ),
    path("recepcao/pessoas/", recepcao.pessoas, name="pessoas"),
    path("recepcao/pessoas/nova/", recepcao.pessoa, name="pessoa_nova"),
    path("recepcao/pessoas/<int:pk>/", recepcao.pessoa, name="pessoa"),
    path("recepcao/regras/", recepcao.regras, name="regras"),
]
