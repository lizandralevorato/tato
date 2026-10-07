from django import forms

from apps.agenda.models import Unidade

from .models import Comunicado


class ComunicadoForm(forms.ModelForm):
    avisar = forms.BooleanField(
        label="avisar no celular agora",
        required=False,
        help_text="Envia uma notificação para quem ativou os avisos no celular.",
    )

    class Meta:
        model = Comunicado
        fields = ["titulo", "texto", "publico", "unidade", "ativo"]
        widgets = {"publico": forms.RadioSelect, "texto": forms.Textarea(attrs={"rows": 6})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = Unidade.objects.filter(ativa=True)
        self.fields["unidade"].empty_label = "Todas as unidades"
        self.fields["unidade"].help_text = ""
        self.fields["ativo"].help_text = "Desmarque para esconder o comunicado sem apagar."
