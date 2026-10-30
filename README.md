# TATO: Agenda que fala

Site acessível para colaboradores agendarem massagem e para massoterapeutas (com diferentes
níveis de deficiência visual) acompanharem a própria agenda pelo celular.

- Plano completo e decisões: [PLANO.md](PLANO.md)
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
| `recepcao` | Recepção (também é superusuário e acessa `/admin/`) | padrão |
| `gestao` | Gestão (entra no painel) | padrão |
| `carlos` | Massoterapeuta | alto contraste escuro, texto 200%, fala ligada |
| `andre` | Massoterapeuta | escuro, texto 150% |
| `marcos` | Massoterapeuta | fala ligada, modo simplificado |
| `lucia` | Massoterapeuta (só manhã) | alto contraste claro, texto 250%, letra legível |
| `ana`, `bruno`, `carla` | Colaboradores | primeiro acesso (passam pelas preferências) |

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
- `tests/test_recepcao.py`: agendar para alguém, encaixe, exceção às regras, histórico, cadastro de pessoas e regras.
- `tests/test_massoterapeuta.py`: horários semanais, folgas com confirmação de cancelamento.
- `tests/test_lista_espera.py`: aviso de vaga ao cancelar ou liberar, quem sai da lista.
- `tests/test_painel_comunicados.py`: indicadores, CSV, histórico, comunicados, "Como funciona" e Libras.

### Lighthouse

Precisa de Node 18+ e do Google Chrome instalado (ou `CHROME_PATH` apontando para ele).

```bash
npm install
npm run lighthouse
```

- Sobe um servidor próprio na porta 8020 (não atrapalha o da 8010) e roda o Lighthouse em
  19 páginas: públicas, colaborador, massoterapeuta, recepção e gestão.
- Entra sozinho com as contas de `popular_demo` ([lighthouse/entrar.js](lighthouse/entrar.js)),
  então rode `popular_demo` antes. O massoterapeuta é o `carlos` (alto contraste, texto 200%).
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
                        Agendamento, HistoricoAgendamento, ListaEspera
  servicos.py           TODAS as regras de negócio (as views só chamam daqui)
  formatacao.py         "9h20", "amanhã, quinta-feira, 1 de outubro"
  forms.py              horários, ausências, pessoas, regras do benefício
  views/                colaborador, massoterapeuta, recepcao (inclui cadastros), paginas
apps/notificacoes/
  avisos.py             quem é avisado de quê (chamado pelas regras da agenda)
  push.py               envio Web Push e tratamento de falhas
  tarefas.py            lembretes e avisos periódicos (comando `notificacoes`)
apps/comunicados/       comunicados da empresa e quem já leu
apps/painel/            indicadores da gestão, CSV e histórico de alterações
templates/              base.html (skip link, landmarks, regiões aria-live) + componentes/
static/css/             tokens.css (cores/temas), base.css, componentes.css
static/js/anunciador.js aria-live + fala (Web Speech API) + vibração + bipe
static/js/agenda-ao-vivo.js  atualiza a agenda do massoterapeuta a cada 20 s sem perder o foco
static/js/push.js       registra o service worker e o painel "Ativar notificações"
static/js/libras.js     carrega o VLibras só quando a pessoa pede
```

## O que cada pessoa faz no site

- **Colaborador**: agenda em 3 passos, faz check-in, avisa a chegada, cancela, entra na lista de espera de dias lotados e lê comunicados para todos.
- **Massoterapeuta**: vê a agenda do dia ao vivo, marca atendido ou falta, pausa, edita os próprios horários semanais e marca folgas e férias (Meus horários), lê comunicados.
- **Recepção**: agenda do dia por massoterapeuta, agendar ou encaixar alguém (com opção de exceção às regras), detalhes e histórico de cada agendamento, cadastro de pessoas, regras do benefício, comunicados.
- **Gestão**: tudo o que a recepção faz, e entra direto no Painel (ocupação, faltas, cancelamentos, usuários únicos, CSV, histórico).
- **Todos, sem login**: página pública [Como funciona](http://localhost:8010/como-funciona/) e a declaração de acessibilidade.

O admin do Django (`/admin/`) fica só para o superusuário: cadastro de unidades e correções raras.

## Check-in (confirmar que vai)

- O check-in **abre 2 h antes** da massagem e o **prazo é 1 h antes**, com **5 min de tolerância**.
- Sem check-in até o fim da tolerância, a reserva vira **"Liberado (sem check-in)"** e o horário volta para a lista de livres. Não conta no limite semanal.
- Quem agenda com o check-in já aberto (em cima da hora) fica com check-in feito automaticamente.
- Horários que já passaram não são liberados (ficam para o massoterapeuta marcar atendido ou falta).
- A liberação roda no comando `notificacoes` e também antes de listar horários, então funciona mesmo com o processador parado.
- Tudo configurável por unidade na tela *Regras* da recepção (prazo 0 desliga o check-in obrigatório).
- O botão **"Cheguei"** (na porta da sala) continua existindo e agora se chama *chegada* no código.

## Notificações (Fase 2)

- **Web Push** com chaves VAPID próprias (gratuito, sem Firebase). Biblioteca: `pywebpush`.
- **Service worker** em `/sw.js` ([templates/notificacoes/sw.js](templates/notificacoes/sw.js)): mostra a notificação com texto completo, vibração conforme a preferência da pessoa e os botões **Vou / Não vou** no lembrete. Se o site estiver aberto na tela, não duplica: repassa o aviso para a página, que anuncia pelo leitor de tela e atualiza a agenda na hora.
- **Quem recebe o quê**:
  - Massoterapeuta: novo agendamento do dia, chegada ("Ana chegou"), cancelamento do dia, "próximo em 5 minutos".
  - Colaborador: lembrete de check-in no tempo escolhido em Preferências (15, 30, 45 min, 1, 2 ou 3 h antes do prazo; padrão 1 h, igual ao comportamento anterior), último aviso no prazo (1 h antes da massagem), aviso de reserva liberada e aviso quando a recepção cancela. Se o lembrete sair antes de o check-in abrir, ele informa o horário de abertura. Os lembretes têm os botões **Fazer check-in / Não vou**.
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
Para trocar para PostgreSQL, preencha `POSTGRES_*` no `.env` (ver `.env.example`). O driver
(`psycopg[binary]`) já está no `requirements.txt`.
