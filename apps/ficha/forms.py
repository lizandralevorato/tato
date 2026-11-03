from django import forms

from . import privacidade
from .servicos import conteudo_da_ficha
from .vocabulario import Condicao, Frequencia, Intensidade, Pressao, Regiao, nome_curto_regiao

SIM_NAO = [("nao", "Não"), ("sim", "Sim")]


class FichaForm(forms.Form):
    """Ficha de saúde. Tudo é opcional, menos o consentimento (na primeira vez)."""

    regioes = forms.MultipleChoiceField(
        label="Onde você costuma sentir dor ou desconforto?",
        choices=Regiao.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    condicoes = forms.MultipleChoiceField(
        label="Você tem alguma destas condições?",
        choices=Condicao.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Marque só as que quiser contar.",
    )
    condicao_outra = forms.CharField(label="Outra condição (opcional)", max_length=120, required=False)
    dor_cronica = forms.ChoiceField(
        label="Você tem dor crônica? (dor que dura meses)",
        choices=SIM_NAO,
        widget=forms.RadioSelect,
        required=False,
        initial="nao",
    )
    dor_cronica_descricao = forms.CharField(
        label="Dor crônica: se quiser, conte em poucas palavras", max_length=200, required=False
    )
    problema_coluna = forms.ChoiceField(
        label="Você tem algum problema na coluna?",
        choices=SIM_NAO,
        widget=forms.RadioSelect,
        required=False,
        initial="nao",
    )
    problema_coluna_descricao = forms.CharField(
        label="Coluna: se quiser, conte em poucas palavras", max_length=200, required=False
    )
    pressao = forms.ChoiceField(
        label="Que pressão você prefere na massagem?",
        choices=Pressao.choices,
        widget=forms.RadioSelect,
        required=False,
        initial=Pressao.SEM_PREFERENCIA,
    )
    evitar = forms.CharField(
        label="Algo que o massoterapeuta deve evitar",
        max_length=200,
        required=False,
        help_text="Por exemplo: não mexer no pescoço.",
    )
    observacoes = forms.CharField(
        label="Observações gerais",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Até 500 caracteres.",
    )
    consentimento = forms.BooleanField(required=False, label=privacidade.TEXTO_CONSENTIMENTO)
    autoriza_sesmt = forms.BooleanField(required=False, label=privacidade.TEXTO_AUTORIZACAO_SESMT)

    def __init__(self, *args, ficha=None, preselecionar=(), exige_consentimento=True, **kwargs):
        self.exige_consentimento = exige_consentimento
        if "initial" not in kwargs:
            kwargs["initial"] = self._inicial(ficha, preselecionar)
        super().__init__(*args, **kwargs)
        for regiao in Regiao:
            nome = nome_curto_regiao(regiao.value)
            self.fields[f"intensidade_{regiao.value}"] = forms.ChoiceField(
                label=f"Intensidade em {nome}",
                choices=[("", "Prefiro não dizer")] + Intensidade.choices,
                required=False,
            )
            self.fields[f"frequencia_{regiao.value}"] = forms.ChoiceField(
                label=f"Frequência em {nome}",
                choices=[("", "Prefiro não dizer")] + Frequencia.choices,
                required=False,
            )

    @staticmethod
    def _inicial(ficha, preselecionar):
        conteudo = conteudo_da_ficha(ficha)
        inicial = {
            "regioes": sorted(set(conteudo["regioes"]) | {p for p in preselecionar if p in Regiao.values}),
            "condicoes": conteudo["condicoes"],
            "condicao_outra": conteudo["condicao_outra"],
            "dor_cronica": "sim" if conteudo["dor_cronica"] else "nao",
            "dor_cronica_descricao": conteudo["dor_cronica_descricao"],
            "problema_coluna": "sim" if conteudo["problema_coluna"] else "nao",
            "problema_coluna_descricao": conteudo["problema_coluna_descricao"],
            "pressao": conteudo["pressao"],
            "evitar": conteudo["evitar"],
            "observacoes": conteudo["observacoes"],
            "autoriza_sesmt": conteudo["autoriza_sesmt"],
        }
        for slug, d in conteudo["regioes"].items():
            inicial[f"intensidade_{slug}"] = d["intensidade"]
            inicial[f"frequencia_{slug}"] = d["frequencia"]
        return inicial

    def clean(self):
        dados = super().clean()
        if self.exige_consentimento and not dados.get("consentimento"):
            self.add_error("consentimento", "Marque a caixa para salvar. Sem o seu aceite, não guardamos a ficha.")
        return dados

    @property
    def linhas_regioes(self):
        """Uma linha por região: caixa de marcar, intensidade e frequência."""
        caixas = {caixa.data["value"]: caixa for caixa in self["regioes"]}
        return [
            {
                "slug": regiao.value,
                "marca": caixas[regiao.value],
                "intensidade": self[f"intensidade_{regiao.value}"],
                "frequencia": self[f"frequencia_{regiao.value}"],
            }
            for regiao in Regiao
        ]

    def dados(self) -> dict:
        """Dados prontos para `servicos.salvar_ficha` (só vale depois de `is_valid`)."""
        limpos = self.cleaned_data
        return {
            "regioes": {
                slug: {
                    "intensidade": limpos.get(f"intensidade_{slug}", ""),
                    "frequencia": limpos.get(f"frequencia_{slug}", ""),
                }
                for slug in limpos["regioes"]
            },
            "condicoes": limpos["condicoes"],
            "condicao_outra": limpos["condicao_outra"],
            "dor_cronica": limpos["dor_cronica"] == "sim",
            "dor_cronica_descricao": limpos["dor_cronica_descricao"],
            "problema_coluna": limpos["problema_coluna"] == "sim",
            "problema_coluna_descricao": limpos["problema_coluna_descricao"],
            "pressao": limpos["pressao"] or Pressao.SEM_PREFERENCIA.value,
            "evitar": limpos["evitar"],
            "observacoes": limpos["observacoes"],
            "autoriza_sesmt": limpos["autoriza_sesmt"],
        }
