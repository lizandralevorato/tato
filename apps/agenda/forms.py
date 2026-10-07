from datetime import datetime, time, timedelta

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from apps.contas.models import Usuario

from .models import Bloqueio, Disponibilidade, PoliticaBeneficio, Unidade

CAMPO_HORA = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
CAMPO_DATA = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class PeriodoForm(forms.Form):
    dia_semana = forms.TypedChoiceField(
        label="Dia da semana", choices=Disponibilidade.DiaSemana.choices, coerce=int
    )
    hora_inicio = forms.TimeField(label="Começa às", widget=CAMPO_HORA)
    hora_fim = forms.TimeField(label="Termina às", widget=CAMPO_HORA)


class AusenciaForm(forms.Form):
    MOTIVOS = [
        (Bloqueio.Motivo.FOLGA, "Folga"),
        (Bloqueio.Motivo.FERIAS, "Férias"),
        (Bloqueio.Motivo.OUTRO, "Outro motivo"),
    ]

    motivo = forms.ChoiceField(label="Motivo", choices=MOTIVOS, widget=forms.RadioSelect, initial=Bloqueio.Motivo.FOLGA)
    data_inicio = forms.DateField(label="Primeiro dia", widget=CAMPO_DATA)
    data_fim = forms.DateField(
        label="Último dia", widget=CAMPO_DATA, required=False, help_text="Deixe em branco se for um dia só."
    )
    hora_inicio = forms.TimeField(
        label="A partir de (opcional)",
        widget=CAMPO_HORA,
        required=False,
        help_text="Só para ausência de parte do dia. Em branco, vale o dia inteiro.",
    )
    hora_fim = forms.TimeField(label="Até (opcional)", widget=CAMPO_HORA, required=False)
    observacao = forms.CharField(label="Observação (opcional)", max_length=200, required=False)
    cancelar_agendamentos = forms.BooleanField(required=False)

    def clean(self):
        dados = super().clean()
        inicio_dia = dados.get("data_inicio")
        if not inicio_dia:
            return dados
        fim_dia = dados.get("data_fim") or inicio_dia
        if fim_dia < inicio_dia:
            self.add_error("data_fim", "O último dia precisa ser igual ou depois do primeiro.")
            return dados
        hora_ini = dados.get("hora_inicio") or time.min
        inicio = timezone.make_aware(datetime.combine(inicio_dia, hora_ini))
        if dados.get("hora_fim"):
            fim = timezone.make_aware(datetime.combine(fim_dia, dados["hora_fim"]))
        else:
            fim = timezone.make_aware(datetime.combine(fim_dia + timedelta(days=1), time.min))
        if fim <= inicio:
            self.add_error("hora_fim", "O fim precisa ser depois do início.")
        dados["inicio"], dados["fim"] = inicio, fim
        return dados


class PoliticaForm(forms.ModelForm):
    class Meta:
        model = PoliticaBeneficio
        exclude = ["unidade"]
        help_texts = {
            "falta_conta_no_limite": "Quem falta perde aquela massagem da semana.",
            "checkin_abre_min": "120 minutos = o check-in abre 2 horas antes.",
            "checkin_prazo_min": "60 minutos = o check-in precisa ser feito até 1 hora antes.",
            "checkin_tolerancia_min": "Depois desse tempo sem check-in, a reserva é liberada para outra pessoa.",
        }


class PessoaForm(forms.Form):
    first_name = forms.CharField(label="Nome", max_length=150)
    last_name = forms.CharField(label="Sobrenome", max_length=150, required=False)
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"autocomplete": "off"}))
    papel = forms.ChoiceField(label="Papel", choices=Usuario.Papel.choices, widget=forms.RadioSelect)
    unidade = forms.ModelChoiceField(label="Unidade", queryset=Unidade.objects.filter(ativa=True), empty_label=None)
    is_active = forms.BooleanField(
        label="acesso ativo", required=False, initial=True, help_text="Desmarque para impedir a entrada no site."
    )
    nova_senha = forms.CharField(
        label="Senha",
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Pelo menos 8 caracteres. Passe para a pessoa e peça para guardar.",
    )
    duracao_sessao_min = forms.IntegerField(label="Duração da sessão (minutos)", min_value=5, max_value=120, initial=20)
    intervalo_min = forms.IntegerField(label="Intervalo entre sessões (minutos)", min_value=0, max_value=120, initial=20)
    atendendo = forms.BooleanField(
        label="atendendo", required=False, initial=True,
        help_text="Desmarque para os horários desta pessoa saírem da agenda (afastamento, desligamento).",
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance is not None and "initial" not in kwargs:
            inicial = {
                "first_name": instance.first_name,
                "last_name": instance.last_name,
                "email": instance.email,
                "papel": instance.papel,
                "unidade": instance.unidade_id,
                "is_active": instance.is_active,
            }
            massoterapeuta = getattr(instance, "massoterapeuta", None)
            if massoterapeuta:
                inicial.update(
                    duracao_sessao_min=massoterapeuta.duracao_sessao_min,
                    intervalo_min=massoterapeuta.intervalo_min,
                    atendendo=massoterapeuta.ativo,
                )
            kwargs["initial"] = inicial
        super().__init__(*args, **kwargs)
        if instance is None:
            self.fields["nova_senha"].required = True
        else:
            self.fields["nova_senha"].label = "Nova senha (opcional)"
            self.fields["nova_senha"].help_text = "Deixe em branco para manter a senha atual."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        outros = Usuario.objects.filter(email__iexact=email)
        if self.instance is not None:
            outros = outros.exclude(pk=self.instance.pk)
        if outros.exists():
            raise forms.ValidationError("Já existe uma pessoa com esse e-mail.")
        return email

    def clean_nova_senha(self):
        senha = self.cleaned_data.get("nova_senha")
        if senha:
            validate_password(senha, self.instance)
        return senha

    def clean(self):
        dados = super().clean()
        papel = dados.get("papel")
        massoterapeuta = getattr(self.instance, "massoterapeuta", None) if self.instance else None
        if massoterapeuta and papel and papel != Usuario.Papel.MASSOTERAPEUTA and massoterapeuta.agendamentos.exists():
            self.add_error(
                "papel",
                "Esta pessoa já atendeu ou tem atendimentos marcados como massoterapeuta. "
                "Para ela parar de atender, desmarque Atendendo.",
            )
        return dados
