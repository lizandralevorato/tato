# TATO: Agenda que fala

Site acessível para colaboradores agendarem massagem e para massoterapeutas (com diferentes
níveis de deficiência visual) acompanharem a própria agenda pelo celular.

- Plano completo e decisões: [PLANO.md](PLANO.md)
- Publicar na internet (Docker): [DEPLOY.md](DEPLOY.md)
- Stack: Django 5.2 LTS (back e front, templates) + JavaScript mínimo, SQLite local
- Paleta: DT-WBS (`#8A38FE`, `#08A0FF`, `#12DA76`, Open Sans), ajustada para contraste AAA
  em [static/css/tokens.css](static/css/tokens.css)

## Rodar localmente (Windows)

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe manage.py migrate
.venv/Scripts/python.exe manage.py popular_demo
.venv/Scripts/python.exe manage.py runserver 8010
```

Abra http://localhost:8010.

Atalhos via npm: `npm run start` (servidor), `npm run migrate`, `npm test` e `npm run notificacoes` (processador de avisos).
Para as notificações, gere as chaves uma vez e rode o processador em outro terminal:

```bash
.venv/Scripts/python.exe manage.py gerar_chaves_vapid
```

Cole as três linhas no `.env` e depois:

```bash
.venv/Scripts/python.exe manage.py notificacoes --continuo
```

> Nesta máquina o Python está com a instalação dividida (executável em `C:\Python314`,
> biblioteca em `AppData\Local\Programs\Python\Python314`). Se `python -m venv` falhar com
> "Could not find platform independent libraries", rode antes:
> `export PYTHONHOME='C:\Users\<usuario>\AppData\Local\Programs\Python\Python314'`.
> Depois de criado, o `.venv` funciona sem isso.

### Contas de demonstração

`popular_demo` cria contas fictícias `<apelido>@demo.local` (a senha está na constante
`SENHA_DEMO` em `apps/agenda/management/commands/popular_demo.py`):

| Apelido | Papel | Preferências de teste |
|---|---|---|
| `administrador` | Administrador (também é superusuário e acessa `/admin/`) | padrão |
| `sesmt` | SESMT (entra no painel) | padrão |
| `carlos` | Massoterapeuta | alto contraste escuro, texto 200%, fala ligada |
| `andre` | Massoterapeuta | escuro, texto 150% |
| `marcos` | Massoterapeuta | fala ligada, modo simplificado |
| `lucia` | Massoterapeuta (só manhã) | alto contraste claro, texto 250%, letra legível |
| `ana`, `bruno`, `carla` | Colaboradores | primeiro acesso (passam pelas preferências) |

Fichas de saúde fictícias: a **Ana** (completa, com alertas e região recorrente: ombros, 3x em 30 dias) e o
**Bruno** (parcial). A **Carla** fica sem ficha. Para testar o botão **Ver ficha** do massoterapeuta, que só
existe de 2 h antes até 1 h depois do atendimento, rode `manage.py popular_demo --agora`: cria um atendimento da
Ana com o Carlos daqui a 30 minutos.

## Testes

```bash
.venv/Scripts/python.exe -m pytest
```

- `tests/test_servicos.py`: regras do benefício (limite semanal, um por dia, cancelamento,
  check-in, falta, conflito de horário, pausa).
- `tests/test_telas.py`: permissões, fluxo de agendamento e checagens estruturais de
  acessibilidade em todas as páginas (`lang`, um `h1`, link "pular", rótulos de campos,
  ids únicos, zoom liberado).
- `tests/test_notificacoes.py`: quem recebe cada aviso, lembrete (janela, sem duplicar), falhas de envio, link assinado, inscrição do aparelho, service worker.
- `tests/test_administrador.py`: agendar para alguém, encaixe, exceção às regras, histórico, cadastro de pessoas e regras.
- `tests/test_massoterapeuta.py`: horários semanais, folgas com confirmação de cancelamento.
- `tests/test_lista_espera.py`: aviso de vaga ao cancelar ou liberar, quem sai da lista.
- `tests/test_painel_comunicados.py`: indicadores, CSV, histórico, comunicados, "Como funciona" e Libras.
- Ficha de saúde: `tests/test_ficha_modelos.py` (migrações reversíveis, versões imutáveis, palavras de região),
  `test_ficha_colaborador.py` (criar, editar, apagar, consentimento, privacidade),
  `test_pedido_sessao.py` (foco e observação em cada agendamento, edição até o check-in abrir),
  `test_ficha_recorrencia.py` (janela, limite, sugestão, convite, Regras),
  `test_ficha_massoterapeuta.py` (janela de acesso, 403/404 por perfil, registro de acesso, resumo da agenda, fala) e
  `test_painel_saude.py` (painel do SESMT, planilha agregada, registro de acessos, o administrador não vê a ficha).

### Lighthouse

Precisa de Node 18+ e do Google Chrome instalado (ou `CHROME_PATH` apontando para ele).

```bash
npm install
npm run lighthouse
```

- Sobe um servidor próprio na porta 8020 (não atrapalha o da 8010) e roda o Lighthouse em
  25 páginas: públicas, colaborador, massoterapeuta, administrador e SESMT.
- Entra sozinho com as contas de `popular_demo` ([lighthouse/entrar.js](lighthouse/entrar.js)),
  então rode `popular_demo` antes. O massoterapeuta é o `carlos` (alto contraste, texto 200%).
- A página da ficha de um atendimento (`/massoterapeuta/atendimentos/<id>/ficha/`) não está na lista: ela só abre
  dentro da janela de horário. As checagens de acessibilidade dela rodam nos testes (`test_ficha_massoterapeuta.py`).
- **Falha se alguma página ficar abaixo de 100 em acessibilidade.** Desempenho, boas práticas
  e SEO só avisam (o servidor é o de desenvolvimento).
- Relatórios em HTML, em português, ficam em `.lighthouseci/relatorios/`.
- Páginas e contas: [lighthouserc.js](lighthouserc.js) e [lighthouse/entrar.js](lighthouse/entrar.js).

Checagem automática não substitui o teste manual com TalkBack, VoiceOver, NVDA e teclado,
nem o teste com os massoterapeutas (ver PLANO.md, seção 7).

## Estrutura

```
config/                 settings e urls
apps/contas/            usuário (login por e-mail), papéis, PerfilAcessibilidade
apps/agenda/
  models.py             Unidade, PoliticaBeneficio, Massoterapeuta, Disponibilidade, Bloqueio,
                        Agendamento (com foco e observação da sessão), HistoricoAgendamento, ListaEspera
  servicos.py           TODAS as regras de negócio (as views só chamam daqui)
  formatacao.py         "9h20", "amanhã, quinta-feira, 1 de outubro"
  forms.py              horários, ausências, pessoas, regras do benefício, pedido da sessão
  views/                colaborador, massoterapeuta, administrador (inclui cadastros), paginas
apps/ficha/             ficha de saúde (dado sensível, LGPD)
  vocabulario.py        regiões do corpo, condições, pressão e sinônimos: o vocabulário único
  models.py             FichaSaude, FichaRegiao, FichaVersao (imutável), AcessoFicha, ApagamentoFicha...
  servicos.py           salvar/apagar, versões, recorrência, sugestões, janela de acesso, resumo
  permissoes.py         decoradores estritos (o superusuário NÃO passa por cima do papel)
  privacidade.py        texto do consentimento e do aviso (com versão)
  indicadores.py        números do painel de saúde do SESMT
apps/notificacoes/
  avisos.py             quem é avisado de quê (chamado pelas regras da agenda)
  push.py               envio Web Push e tratamento de falhas
  tarefas.py            lembretes e avisos periódicos (comando `notificacoes`)
apps/comunicados/       comunicados da empresa e quem já leu
apps/painel/            indicadores do SESMT, CSV, histórico de alterações e painel de saúde (saude.py)
templates/              base.html (skip link, landmarks, regiões aria-live) + componentes/
static/css/             tokens.css (cores/temas), base.css, componentes.css
static/js/anunciador.js aria-live + fala (Web Speech API) + vibração + bipe
static/js/agenda-ao-vivo.js  atualiza a agenda do massoterapeuta a cada 20 s sem perder o foco
static/js/ficha-etapas.js    ficha em 3 etapas (sem JS, as 3 aparecem juntas)
static/js/ouvir-ficha.js     "Ouvir ficha": lê a própria tela, com pausar, continuar e repetir
static/js/contador.js        contador de caracteres que não fala a cada tecla
static/js/push.js       registra o service worker e o painel "Ativar notificações"
static/js/libras.js     carrega o VLibras só quando a pessoa pede
```

## O que cada pessoa faz no site

- **Colaborador**: agenda em 3 passos, faz check-in, avisa a chegada, cancela, entra na lista de espera de dias lotados e lê comunicados para todos. Se quiser, preenche a **ficha de saúde** (opcional, em 3 etapas, pode mudar ou apagar quando quiser) e, ao confirmar uma massagem, conta onde quer focar naquele dia.
- **Massoterapeuta**: vê a agenda do dia ao vivo, com o foco de cada atendimento, marca atendido ou falta, pausa, edita os próprios horários semanais e marca folgas e férias (Meus horários), lê comunicados. Abre a ficha de **uma pessoa por vez**, só dos próprios atendimentos, de 2 h antes até 1 h depois, e pode ouvi-la.
- **Administrador**: agenda do dia por massoterapeuta, agendar ou encaixar alguém (com opção de exceção às regras), detalhes e histórico de cada agendamento (com a observação da sessão), cadastro de pessoas, regras do benefício, comunicados. **Não vê fichas de saúde**: só sabe se a ficha existe e se está atualizada.
- **SESMT**: tudo o que o administrador faz, e entra direto no Painel (ocupação, faltas, cancelamentos, usuários únicos, CSV, histórico). É o único perfil que vê as fichas: painel **Saúde e foco** (regiões, condições, fichas preenchidas e desatualizadas, regiões recorrentes), ficha individual com histórico de versões, registro de acessos e planilha agregada.
- **Todos, sem login**: página pública [Como funciona](http://localhost:8010/como-funciona/), a declaração de acessibilidade e o aviso de [privacidade da ficha](http://localhost:8010/privacidade-da-ficha/).

O admin do Django (`/admin/`) fica só para o superusuário (os programadores): cadastro de unidades e correções raras. **Os modelos da ficha de saúde não estão registrados nele de propósito.**

## Ficha de saúde e pedido da sessão

- **Ficha (por pessoa):** regiões com dor (intensidade e frequência), condições, dor crônica, problema na coluna, preferência de pressão, o que evitar e observações. Tudo opcional, menos o aceite do aviso de privacidade (data, hora e versão do texto ficam gravados). Cada salvamento grava uma versão imutável (quem, quando, o que mudou). Apagar a ficha apaga também as versões; fica só o registro de que foi apagada.
- **Pedido da sessão:** no passo 3 da reserva (e nos encaixes do administrador), foco por regiões e até 300 caracteres. Editável até o check-in abrir. Se a reserva é cancelada, o texto fica no histórico e some da tela do massoterapeuta.
- **Região recorrente:** o sistema conta, por pessoa, quantas vezes cada região aparece no foco dos agendamentos realizados ou marcados na janela (padrão 3 vezes em 30 dias; janela e limite em **Regras**, por unidade). Palavras do texto livre só apoiam e nunca marcam sozinhas. Quando passa do limite, o massoterapeuta e o SESMT veem o aviso, e a pessoa recebe a sugestão "Quer adicionar na sua ficha?" (a ficha só muda se ela aceitar; "Agora não" silencia a região por 30 dias). **É um sinal de atenção, não um diagnóstico.**
- **Quem vê o quê:** o massoterapeuta só abre a ficha de um atendimento dele, de 2 h antes até 1 h depois (fora disso, 403; atendimento de outro massoterapeuta, 404). A lista da agenda traz só foco, região recorrente, o pedido da pessoa e um aviso de que a ficha tem alertas, **nunca** o conteúdo da ficha, e a página aberta mostra a ficha inteira mais o pedido da sessão. O SESMT vê tudo com registro de acesso. O administrador não vê a ficha. O superusuário também não passa na checagem da ficha.
- **Privacidade na voz e nos avisos:** o botão "Ouvir agenda de hoje" fala só horário, nome e foco. "Ouvir ficha" mostra o aviso de fones na primeira vez. Notificações no celular nunca levam texto livre nem dado de saúde.
- **Planilha:** só a agregada (contagens por região e condição, sem nome, grupos com menos de 3 pessoas aparecem como "menos de 3"), só para o SESMT e com registro.

## Check-in (confirmar que vai)

- O check-in **abre 2 h antes** da massagem e o **prazo é 1 h antes**, com **5 min de tolerância**.
- Sem check-in até o fim da tolerância, a reserva vira **"Liberado (sem check-in)"** e o horário volta para a lista de livres. Não conta no limite semanal.
- Quem agenda com o check-in já aberto (em cima da hora) fica com check-in feito automaticamente.
- Horários que já passaram não são liberados (ficam para o massoterapeuta marcar atendido ou falta).
- A liberação roda no comando `notificacoes` e também antes de listar horários, então funciona mesmo com o processador parado.
- Tudo configurável por unidade na tela *Regras* do administrador (prazo 0 desliga o check-in obrigatório).
- O botão **"Cheguei"** (na porta da sala) continua existindo e agora se chama *chegada* no código.

## Notificações (Fase 2)

- **Web Push** com chaves VAPID próprias (gratuito, sem Firebase). Biblioteca: `pywebpush`.
- **Service worker** em `/sw.js` ([templates/notificacoes/sw.js](templates/notificacoes/sw.js)): mostra a notificação com texto completo, vibração conforme a preferência da pessoa e os botões **Vou / Não vou** no lembrete. Se o site estiver aberto na tela, não duplica: repassa o aviso para a página, que anuncia pelo leitor de tela e atualiza a agenda na hora.
- **Quem recebe o quê**:
  - Massoterapeuta: novo agendamento do dia, chegada ("Ana chegou"), cancelamento do dia, "próximo em 5 minutos".
  - Colaborador: lembrete de check-in no tempo escolhido em Preferências (15, 30, 45 min, 1, 2 ou 3 h antes do prazo; padrão 1 h, igual ao comportamento anterior), último aviso no prazo (1 h antes da massagem), aviso de reserva liberada e aviso quando o administrador cancela. Se o lembrete sair antes de o check-in abrir, ele informa o horário de abertura. Os lembretes têm os botões **Fazer check-in / Não vou**.
  - Massoterapeuta e todos: comunicados, se quem publicou marcar "avisar no celular".
  - Lista de espera: aviso "Abriu uma vaga" quando alguém cancela ou uma reserva é liberada.
  - Tempos configuráveis por unidade na tela Regras (0 desliga).
- **Lembrete sem login**: o link da notificação é assinado, vale só para aquele agendamento e expira em 2 dias ([apps/notificacoes/tokens.py](apps/notificacoes/tokens.py)).
- **Processador periódico**: `manage.py notificacoes` (um ciclo) ou `--continuo`. Em servidor, agende a cada minuto (Agendador de Tarefas do Windows, cron ou systemd). É idempotente: o banco impede o mesmo aviso duas vezes.
- **Falhas**: aparelho que desinstalou (410) é removido; erro de rede é reenviado nos ciclos seguintes (até 5 tentativas em 30 min). Tudo fica em *Notificações* no admin.

### Testar no celular

Service worker e push só funcionam em **HTTPS** (ou em `localhost` no próprio aparelho). Para testar no celular antes de ter servidor, use um túnel HTTPS gratuito (por exemplo Cloudflare Tunnel: `cloudflared tunnel --url http://localhost:8010`) e adicione o domínio do túnel em `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS`.

- **Android (Chrome)**: Preferências → *Ativar notificações neste aparelho* → *Enviar notificação de teste*.
- **iPhone (iOS 16.4+)**: primeiro *Compartilhar → Adicionar à Tela de Início*, abrir pelo ícone, e só então ativar. O iPhone não vibra por sites.

## Banco de dados

Local, em SQLite (`db.sqlite3`), sem configuração. A restrição que impede dois agendamentos
no mesmo horário é um índice único parcial, suportado tanto no SQLite quanto no PostgreSQL.
Para trocar para PostgreSQL, preencha `POSTGRES_*` ou `DATABASE_URL` no `.env` (ver `.env.example`).
O driver (`psycopg[binary]`) já está no `requirements.txt`. Em produção, use PostgreSQL (ver [DEPLOY.md](DEPLOY.md)).
