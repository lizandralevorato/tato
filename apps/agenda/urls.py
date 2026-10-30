from django.urls import path

from .views import colaborador, massoterapeuta, administrador

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
    # Administrador e SESMT
    path("administrador/", administrador.agenda_da_unidade, name="administrador"),
    path("administrador/agendar/", administrador.agendar_para, name="administrador_agendar"),
    path("administrador/agendamentos/<int:pk>/", administrador.agendamento_detalhe, name="administrador_agendamento"),
    path(
        "administrador/agendamentos/<int:pk>/<str:acao>/", administrador.marcar_pela_equipe, name="administrador_marcar"
    ),
    path("administrador/pessoas/", administrador.pessoas, name="pessoas"),
    path("administrador/pessoas/nova/", administrador.pessoa, name="pessoa_nova"),
    path("administrador/pessoas/<int:pk>/", administrador.pessoa, name="pessoa"),
    path("administrador/regras/", administrador.regras, name="regras"),
]
