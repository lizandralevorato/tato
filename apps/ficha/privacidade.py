"""Texto do consentimento (LGPD) e do aviso de privacidade da ficha.

Mudou o texto? Aumente VERSAO_TEXTO. Quem aceitou uma versão antiga precisa aceitar
de novo na próxima vez que salvar a ficha.
"""

VERSAO_TEXTO = "2026-11"

TEXTO_CONSENTIMENTO = (
    "Eu entendo e aceito que o TATO guarde as informações de saúde que eu escolher preencher "
    "nesta ficha, para o massoterapeuta que me atende se preparar."
)

TEXTO_AUTORIZACAO_SESMT = (
    "Opcional: eu autorizo o SESMT a ver a minha ficha com o meu nome, para acompanhar a minha saúde. "
    "Se eu não marcar, o SESMT só vê contagens do grupo, sem o meu nome. Posso mudar isso quando quiser."
)

# (título, parágrafo): cada item vira um bloco do aviso, na tela da ficha e na página de privacidade.
AVISO = [
    (
        "O que guardamos",
        "Só o que você preencher: onde costuma sentir dor ou desconforto (com intensidade e frequência), "
        "condições de saúde, dor crônica, problema na coluna, preferência de pressão, algo que o massoterapeuta "
        "deve evitar e observações. Tudo é opcional.",
    ),
    (
        "Por que é dado sensível",
        "Informações de saúde são dados pessoais sensíveis pela Lei Geral de Proteção de Dados (LGPD). "
        "Por isso pedimos o seu consentimento e guardamos com cuidado.",
    ),
    (
        "Quem pode ver",
        "O massoterapeuta que atende você só abre a sua ficha de 2 horas antes até "
        "1 hora depois do seu horário, e só a do atendimento dele. O SESMT só vê a sua ficha com o seu nome se você "
        "autorizar no fim do preenchimento; sem a autorização, ele vê apenas contagens do grupo, sem nome. "
        "O administrador do site não vê a sua ficha. "
        "Cada vez que alguém abre a ficha, o acesso fica registrado, e você pode consultar esse registro.",
    ),
    (
        "Para que serve",
        "Para o massoterapeuta saber onde focar e o que evitar, e para o SESMT entender, em contagens sem nome, onde as pessoas "
        "sentem mais desconforto e planejar ações de saúde. Não é um diagnóstico e não substitui consulta médica.",
    ),
    (
        "Seus direitos",
        "Você pode mudar a ficha quando quiser, e apagar tudo a qualquer momento em Minha ficha de saúde. "
        "Ao apagar, o conteúdo e o histórico de versões são eliminados. Fica só o registro de que a ficha foi "
        "apagada e quando. Você também pode retirar o consentimento apagando a ficha.",
    ),
    (
        "Observação de cada massagem",
        "O que você escrever ao agendar vale só para aquela massagem. Quem agenda, o massoterapeuta que atende, "
        "o administrador e o SESMT podem ler. Não escreva nada que você não queira que essas pessoas leiam.",
    ),
]

AVISO_NAO_E_DIAGNOSTICO = (
    "Isto não é um diagnóstico. É só um sinal para o massoterapeuta e o SESMT darem atenção."
)
