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
        fields = ["titulo", "texto", "nivel", "publico", "unidade", "data_inicio", "data_fim", "ativo"]
        widgets = {
            "publico": forms.RadioSelect,
            "nivel": forms.RadioSelect,
            "texto": forms.Textarea(attrs={"rows": 6}),
            "data_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "data_fim": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = Unidade.objects.filter(ativa=True)
        self.fields["unidade"].empty_label = "Todas as unidades"
        self.fields["unidade"].help_text = ""
        self.fields["ativo"].help_text = "Desmarque para esconder o comunicado sem apagar."

    def clean(self):
        dados = super().clean()
        inicio, fim = dados.get("data_inicio"), dados.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data final não pode ser antes da data inicial.")
        return dados
