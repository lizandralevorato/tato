from django.urls import path

from .views import colaborador, massoterapeuta

app_name = "ficha"

urlpatterns = [
    path("massoterapeuta/atendimentos/<int:pk>/ficha/", massoterapeuta.ficha_do_atendimento, name="do_atendimento"),
    path("massoterapeuta/aviso-fala-ficha/", massoterapeuta.ocultar_aviso_fala, name="ocultar_aviso_fala"),
    path("minha-ficha/", colaborador.minha_ficha, name="minha"),
    path("minha-ficha/apagar/", colaborador.apagar_ficha, name="apagar"),
    path("minha-ficha/acessos/", colaborador.meus_acessos, name="meus_acessos"),
    path("minha-ficha/convite/agora-nao/", colaborador.convite_agora_nao, name="agora_nao"),
    path("minha-ficha/sugestao/dispensar/", colaborador.dispensar_sugestao, name="dispensar"),
    path("privacidade-da-ficha/", colaborador.privacidade_da_ficha, name="privacidade"),
]
