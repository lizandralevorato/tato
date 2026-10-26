from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import PerfilAcessibilidade


class EntrarForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "E-mail ou senha incorretos. Confira e tente de novo.",
        "inactive": "Este acesso está desativado. Fale com a recepção.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "E-mail"
        self.fields["username"].widget = forms.EmailInput(
            attrs={"autocomplete": "email", "inputmode": "email", "autocapitalize": "none"}
        )
        self.fields["password"].label = "Senha"
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class PreferenciasForm(forms.ModelForm):
    class Meta:
        model = PerfilAcessibilidade
        fields = [
            "tamanho_texto",
            "fonte",
            "espacamento_ampliado",
            "tema",
            "reduzir_movimento",
            "modo_simplificado",
            "fala_ativa",
            "fala_velocidade",
            "lembrete_checkin_min",
            "vibracao",
            "som",
            "libras",
        ]
        widgets = {
            "tamanho_texto": forms.RadioSelect,
            "fonte": forms.RadioSelect,
            "tema": forms.RadioSelect,
            "fala_velocidade": forms.RadioSelect,
            "lembrete_checkin_min": forms.RadioSelect,
        }
        help_texts = {
            "lembrete_checkin_min": (
                "Você recebe um lembrete da massagem neste tempo antes do prazo do check-in. "
                "Se não fizer o check-in, ainda recebe um último aviso no prazo, antes de a reserva ser liberada."
            ),
            "fala_ativa": (
                "O site fala sozinho quando alguém chega, cancela ou quando o próximo "
                "atendimento está perto. Se você já usa TalkBack ou VoiceOver, teste "
                "antes: as duas vozes podem falar ao mesmo tempo."
            ),
            "vibracao": "Funciona em celulares Android. O iPhone não permite vibração por sites.",
            "modo_simplificado": "Esconde informações secundárias e mostra uma tarefa por vez.",
            "libras": "Mostra o botão do VLibras, que traduz os textos da tela para Libras. "
            "Mesmo desligado, você pode abri-lo pelo link Traduzir para Libras, no rodapé.",
        }
