# Plano: Plataforma de Agendamento de Massagem (acessível)

> Base: planilha *DISCOVERY PROJETO ESTÁGIO* (entrevistas com Silvana e Cláudio, set/2026).
> Stack: **Django full-stack** (templates + JavaScript mínimo), **PWA** instalável no celular, **SQLite local** (PostgreSQL quando for para servidor). Paleta **DT-WBS**.

---

## 1. Objetivo e escopo

Substituir a planilha da Silvana + Teams por um site onde:

| Perfil | O que faz |
|---|---|
| **Colaborador** | Vê horários livres, agenda, confirma presença ("vou / não vou"), cancela, faz check-in ("Cheguei") |
| **Massoterapeuta** (baixa visão ou cegueira, sem computador corporativo, usa o **celular**) | Ouve/vê a agenda do dia, recebe aviso por voz/vibração de check-in e cancelamento, marca "atendido / faltou", pausa a agenda (água/banheiro), gerencia a própria disponibilidade |
| **Administrador/Admin** (Silvana) | Trata exceções, faz encaixes, cadastra massoterapeutas e disponibilidades, vê relatórios |
| **SESMT** | Painel com ocupação, faltas, usuários únicos |

### Como cada problema do discovery é resolvido

| # | Problema (ranking) | Solução no sistema | Fase |
|---|---|---|---|
| 1 | Massoterapeuta não sabe quem vai atender | Tela "Minha agenda de hoje" + avisos por voz/push | 1 |
| 2 | Processo não gera dados | Todo agendamento tem status (realizado/falta/cancelado/encaixe) → painel | 1 e 3 |
| 3 | Sem regras formais | Política configurável e aplicada automaticamente (tolerância 5 min, cancelar até 15 min antes, falta conta no limite, máx. 2/semana em dias diferentes) | 1 |
| 4 | Ferramentas sem acessibilidade | Todo o plano de acessibilidade abaixo | 1→4 |
| 6 | Agendamento centralizado na Silvana | Autoagendamento 24h, Silvana vira administradora | 1 |
| 6 | Limite de 2/semana conferido na mão | Validação automática (conta encaixes e faltas) | 1 |
| 8 | Faltas e cancelamentos sem aviso | Lembrete com "vou / não vou", aviso automático ao massoterapeuta, vaga liberada | 2 |
| 10 | Conflito de horário | Restrição única no banco + check-in | 1 e 2 |
| 4 | Colaboradores não conhecem o benefício | Página pública "Como funciona" + link fácil de divulgar | 4 |
| 9 | Isolamento do massoterapeuta | Área de avisos/comunicados da empresa dentro do app | 4 |

---

## 2. Decisão importante sobre "API de ler a tela"

**Não dá (e não se deve) substituir o leitor de tela das pessoas.** Os massoterapeutas cegos já usam **TalkBack** (Android) ou **VoiceOver** (iPhone), com a voz, a velocidade e os gestos que eles já conhecem. O que faz o site ser acessível é o **HTML bem feito** funcionar perfeitamente com esses leitores.

**Evitar "widgets de acessibilidade" prontos (overlays)** como UserWay, accessiBe, Hand Talk Plugin pago etc.: eles costumam **atrapalhar** quem usa leitor de tela (inserem elementos, mudam foco, conflitam com o TalkBack) e não corrigem o código de verdade.

O que **vale a pena usar (tudo gratuito)**, como complemento:

| Recurso | Para quê | Custo / observação |
|---|---|---|
| **Web Speech API: `speechSynthesis`** (nativa do navegador) | Avisos falados que o leitor de tela não daria sozinho: "Ana fez check-in", "Horário das 9h20 foi cancelado", "Próximo atendimento em 5 minutos". Botão "Ouvir agenda de hoje" | Grátis, sem chave, funciona em Chrome/Android e Safari/iOS. **Configurável por pessoa** (liga/desliga, velocidade) para não "brigar" com o TalkBack |
| **Vibration API** | Padrões de vibração diferentes por evento (check-in = 2 curtas, cancelamento = 1 longa) | Grátis. **Não funciona no iPhone** → no iOS usar som + push |
| **Web Push (VAPID) + `pywebpush`** | Notificação com celular bloqueado (check-in, cancelamento, lembrete) | Grátis, sem Firebase pago. No iPhone exige o site **instalado na tela inicial** (iOS 16.4+) |
| **VLibras** (Governo Federal) | Tradução para Libras de colaboradores surdos | Grátis, script oficial. Carregar sob demanda (botão), não por padrão |
| **Web Speech API: reconhecimento de voz** | (Opcional, fase 4) comandos como "próximo atendimento" | Só Chrome; envia áudio ao Google → avaliar com a empresa |

---

## 3. Requisitos de acessibilidade

"100% acessível" não existe como certificado. A meta concreta é:

- **WCAG 2.2 nível AA em todo o site** e **AAA nos pontos críticos** (contraste 7:1, alvos de toque ≥ 44px, sem limite de tempo).
- Aderência ao **eMAG** e à **Lei Brasileira de Inclusão (Lei 13.146/2015)**.
- **Validação com os próprios massoterapeutas** (Cláudio, Andrey, Matheus, Lindaura) a cada fase. Esse é o critério real de pronto.

### 3.1 Preferências por pessoa (salvas no banco, seguem a pessoa em qualquer aparelho)

Cada um tem uma necessidade diferente (letra grande + modo escuro, ou TalkBack), então o sistema guarda um **Perfil de Acessibilidade** por usuário, com um assistente no primeiro acesso:

- Tamanho do texto: 100% / 125% / 150% / 200% / 250%
- Tema: claro / escuro / **alto contraste escuro** (amarelo sobre preto) / alto contraste claro / seguir o sistema
- Espaçamento ampliado (linhas e letras)
- Reduzir animações
- **Modo simplificado** (uma tarefa por tela, menos elementos)
- Avisos falados: liga/desliga, velocidade da fala, voz
- Vibração: liga/desliga
- Som de notificação: liga/desliga

O servidor aplica as classes direto no `<html>` (ex.: `<html lang="pt-BR" class="tema-ac-escuro fonte-200">`), então **não há "piscada"** de tema errado ao carregar.

### 3.2 Regras de construção (checklist de todo template)

**Estrutura e semântica**
- `lang="pt-BR"`, `<title>` único por página ("Minha agenda | Agenda de Massagem")
- Landmarks: `header`, `nav`, `main`, `footer`; **link "Pular para o conteúdo"** como primeiro elemento
- Um `h1` por página, hierarquia de títulos sem pular níveis (TalkBack navega por títulos)
- HTML nativo antes de ARIA: `<button>`, `<a>`, `<fieldset>/<legend>`, `<input type="radio">`, `<table>` com `<th scope>`

**Agendamento sem "calendário visual"**
- Grades de calendário são ruins com leitor de tela. Fluxo em **listas**: 1) escolher dia (lista) → 2) escolher horário (radio buttons agrupados por massoterapeuta ou por horário) → 3) confirmar
- Cada opção tem rótulo completo: *"Terça, 7 de outubro, 9h20, com Cláudio"*
- Horas lidas de forma natural ("9h20", nunca "09:20:00")

**Formulários e mensagens**
- Todo campo com `<label>` visível; erros com **resumo no topo que recebe o foco** + erro ao lado do campo com `aria-describedby`
- Mensagens de sucesso/erro em região `aria-live` (`polite`; `assertive` só para cancelamento de quem está chegando)
- Ao trocar conteúdo sem recarregar a página: mover o foco para o título da nova seção e anunciar

**Visual**
- Contraste ≥ 7:1 no texto (AAA), ≥ 3:1 em bordas de campos e ícones
- **Foco visível grosso** (outline de 3 a 4px, contraste alto) em todos os temas
- Nunca informar só por cor (status = cor + ícone + texto: "✔ Confirmado")
- Alvos de toque ≥ 44×44px, com espaço entre eles
- Ícones sempre acompanhados de texto

**Responsividade / zoom**
- Mobile-first, unidades `rem`, tipografia fluida com `clamp()`
- Funciona com **zoom de 400% sem rolagem horizontal** (reflow em 320px de largura, WCAG 1.4.10)
- Funciona em retrato e paisagem, de celular pequeno a monitor grande
- Suporta `prefers-color-scheme`, `prefers-reduced-motion`, `prefers-contrast` e `forced-colors` (alto contraste do Windows)

**Tempo e autenticação**
- **Nenhum limite de tempo** no fluxo de agendamento; sessão longa ("manter conectado") para massoterapeutas no celular
- Login sem desafio cognitivo (WCAG 3.3.8): **SSO Google Workspace** (a empresa está migrando) + e-mail/senha como alternativa, permitindo colar e gerenciador de senhas. **Sem CAPTCHA.**

**Conteúdo**
- Linguagem simples, frases curtas, botões com verbos ("Agendar massagem", "Cancelar horário das 9h20")
- Página **Declaração de Acessibilidade** com canal para reportar problemas

---

## 4. Arquitetura técnica

### 4.1 Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Back-end | **Python 3.12+ / Django 5.2 LTS** | Pedido do projeto; LTS até 2028 |
| Front-end | **Templates Django** + CSS próprio com design tokens (paleta DT-WBS) + JavaScript puro mínimo | Site funciona sem JS (progressive enhancement), HTML semântico controlado por nós, sem SPA pesada que costuma quebrar leitores de tela. HTMX foi dispensado: o único ponto dinâmico (agenda ao vivo) precisa de controle fino de foco e anúncios |
| Banco | **SQLite local** agora → **PostgreSQL** ao ir para servidor | SQLite basta para 1 unidade e ~200 atendimentos/semana e não exige instalação; PostgreSQL entra quando houver acesso simultâneo real (várias pessoas agendando ao mesmo tempo, travas de linha) e backup gerenciado. A troca é só configurar `POSTGRES_*` no `.env` |
| Login | Hoje: e-mail + senha (Django). Depois: `django-allauth` com Google Workspace SSO (depende da decisão 2) | |
| Tarefas agendadas (lembretes) | `django-q2` com broker no próprio banco | Sem precisar de Redis |
| Push | `pywebpush` + chaves VAPID | Gratuito |
| Tempo real na tela do massoterapeuta | Polling de um JSON pequeno a cada 20 a 30s (MVP) → Server-Sent Events (fase 4, se necessário) | Simples; o push cobre o celular bloqueado |
| PWA | `manifest.json` + service worker próprio | Instalável, ícone na tela inicial, push no iOS |
| Estáticos | `whitenoise` | |
| Config | `django-environ` | |
| Testes | `pytest-django`, `factory-boy`, **Playwright + axe-core** (`axe-playwright-python`), `pa11y-ci`, Lighthouse CI | |

### 4.2 Estrutura de pastas

```
maso/
├─ config/                 # settings (base/dev/prod), urls, wsgi
├─ apps/
│  ├─ contas/              # User customizado, papéis, PerfilAcessibilidade, login/SSO
│  ├─ agenda/              # Unidade, Massoterapeuta, Disponibilidade, Bloqueio, Agendamento, Política
│  │   └─ services.py      # regras de negócio (geração de horários, validações)
│  ├─ notificacoes/        # lembretes, push, inscrições, tarefas django-q2
│  └─ painel/              # dashboard e relatórios do SESMT
├─ templates/
│  ├─ base.html            # skip link, landmarks, região aria-live, classes de preferência
│  └─ componentes/         # botao, campo, alerta, cartao_agendamento... (acessíveis por padrão)
├─ static/
│  ├─ css/ tokens.css, temas.css, base.css, componentes.css
│  ├─ js/  anunciador.js (aria-live + speechSynthesis + vibração), push.js
│  ├─ sw.js
│  └─ manifest.json
└─ tests/  unit/, a11y/ (Playwright + axe)
```

### 4.3 Modelo de dados

```
Unidade            nome (Londrina, São Paulo), fuso, ativa
User (custom)      nome, e-mail, papel [colaborador | massoterapeuta | administrador | sesmt], unidade
PerfilAcessibilidade  user (1:1), tamanho_fonte, tema, espacamento, reduzir_movimento,
                      modo_simplificado, fala_ativa, fala_velocidade, vibracao, som
Massoterapeuta     user (1:1), unidade, duracao_sessao (min), intervalo (min),
                   capacidade_diaria, ativo
Disponibilidade    massoterapeuta, dia_semana, hora_inicio, hora_fim   (recorrente semanal)
Bloqueio           massoterapeuta, inicio, fim, motivo [folga, férias, pausa, outro]
PoliticaBeneficio  unidade, max_por_semana=2, dias_diferentes=True, tolerancia_min=5,
                   antecedencia_cancelamento_min=15, falta_conta_no_limite=True,
                   lembrete_min_antes
Agendamento        colaborador, massoterapeuta, inicio, fim,
                   status [agendado, confirmado, cancelado, checkin, realizado, falta],
                   origem [autoagendamento, administrador, encaixe],
                   criado_em, confirmado_em, cancelado_em, checkin_em, cancelado_por
InscricaoPush      user, endpoint, chaves, user_agent
Comunicado         (fase 4) título, texto, unidade, publicado_em
```

- **Horários livres não são gravados**: são calculados = disponibilidade − bloqueios − agendamentos ativos.
- **Conflito impossível** (problema #10) com restrição no banco + transação:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["massoterapeuta", "inicio"],
            condition=~Q(status__in=["cancelado"]),
            name="um_agendamento_ativo_por_horario",
        ),
    ]
```

- Histórico de alterações (quem cancelou/encaixou) com `django-simple-history` → atende o problema #2 (dados).

### 4.4 Regras de negócio (`agenda/services.py`)

Todas testadas com testes unitários:

1. Horário precisa estar dentro da disponibilidade e fora de bloqueios.
2. Máximo **2 por semana**, em **dias diferentes**; faltas e encaixes **contam**.
3. Cancelamento pelo colaborador só até **15 min antes**; depois disso, só o administrador.
4. Após **5 min** de tolerância sem check-in → massoterapeuta pode marcar falta (ou o sistema sugere).
5. Cancelou → vaga liberada imediatamente para encaixe + aviso ao massoterapeuta.
6. Valores vêm de `PoliticaBeneficio` (Silvana/RH alteram sem mexer no código).

Referência de capacidade (discovery): atendimento das 8h às 11h40 e das 13h às 16h40 (440 min/dia); Cláudio, Andrey e Matheus até 11/dia, Lindaura até 6 → **39/dia, 195/semana**.

---

## 5. Telas

### Colaborador
1. **Início**: "Seus próximos horários" + botão grande "Agendar massagem" + quantas massagens restam na semana
2. **Agendar** (3 passos, cada um uma tela no modo simplificado): dia → horário/massoterapeuta → confirmar
3. **Meus agendamentos**: confirmar ("vou"), cancelar ("não vou"), **"Cheguei"** (check-in, habilitado 10 min antes)
4. **Preferências de acessibilidade**
5. **Como funciona o benefício** (regras em linguagem simples)

### Massoterapeuta (pensada primeiro para TalkBack/VoiceOver e fonte grande)
1. **Agora**: tela inicial com uma única informação principal: *"Próximo: 9h20, Ana Souza, confirmada. Faltam 12 minutos."* + botão "Ouvir agenda de hoje"
2. **Agenda de hoje**: lista cronológica (não tabela), cada item com hora, nome, status em texto
3. Ações por atendimento: **"Atendido"**, **"Faltou"**
4. **"Pausar agenda"** (água/banheiro, 5/10/15 min) → bloqueia encaixes nesse período (resolve a insegurança de sair da sala)
5. **Minha disponibilidade**: dias/horários da semana e folgas, em formulário simples
6. **Preferências** (fala, vibração, tema, fonte)

Avisos em tempo real: check-in, cancelamento, novo encaixe, "próximo em 5 min" → região `aria-live` + fala (se ativada) + vibração + push.

### Administrador (Silvana)
- Agenda do dia de todos os massoterapeutas, **encaixe manual**, cancelar/remarcar por qualquer pessoa
- Cadastro de massoterapeutas, disponibilidades, bloqueios, política do benefício
- Django Admin para cadastros raros (personalizado e testado com teclado)

### SESMT
- Painel: taxa de ocupação, no-show, cancelamentos, encaixes, usuários únicos, por massoterapeuta/unidade/período
- Todo gráfico tem **tabela equivalente** + exportar CSV

---

## 6. Roteiro por fases

### Fase 0: Preparação (1 semana)
- Confirmar decisões em aberto (seção 8)
- Criar repositório git, projeto Django, CI (lint + testes + axe)
- Design tokens e temas (claro, escuro, 2 de alto contraste) + componentes base
- **Protótipo navegável de 3 telas** testado com 1 ou 2 massoterapeutas no celular deles

### Fase 1: MVP de agendamento (3 a 4 semanas) → problemas #1, #3, #4, #6, #10
- Login (SSO + e-mail), papéis, perfil de acessibilidade com assistente de primeiro acesso
- Cadastro de unidade, massoterapeutas, disponibilidade, bloqueios, política
- Cálculo de horários livres + agendamento com todas as regras
- "Meus agendamentos", cancelamento
- Tela "Agora" e "Agenda de hoje" do massoterapeuta com atualização automática + `aria-live`
- Status atendido/faltou
- ✅ **Critério de pronto:** os 4 massoterapeutas conseguem ver a agenda do dia sozinhos, no próprio celular

### Fase 2: Presença e notificações (2 semanas) → problemas #8, #10
- PWA instalável + Web Push
- Lembrete com "vou / não vou" (tarefa `django-q2`)
- Check-in "Cheguei" + aviso falado/vibração ao massoterapeuta
- Pausa da agenda; liberação automática de vaga e encaixe
- Opcional: lista de espera ("me avise se abrir vaga")

### Fase 3: Dados e SESMT (1 a 2 semanas) → problema #2
- Painel do SESMT + tabela + CSV
- Histórico de alterações

### Fase 4: Evolução (contínuo) → problemas #4 (divulgação), #9, SP
- Página "Como funciona" + material de divulgação, VLibras sob demanda
- Comunicados da empresa para massoterapeutas
- Unidade São Paulo (retomada do programa)
- Server-Sent Events se o polling não for suficiente; comandos de voz (se aprovado)

---

## 7. Como garantir a acessibilidade (testes)

| Tipo | Ferramenta | Quando |
|---|---|---|
| Automático | **axe-core via Playwright** em todas as páginas, em cada tema e fonte 200% | Todo commit (CI); o build falha se houver violação |
| Automático | Lighthouse CI (acessibilidade = 100) e `pa11y-ci` | CI |
| Unitário | Regras de negócio (limite semanal, cancelamento, conflito) | CI |
| Manual | Só teclado (Tab/Shift+Tab/Enter/Espaço/Esc) | Toda tela nova |
| Manual | **NVDA** (grátis, Windows) + Chrome/Firefox | Toda tela nova |
| Manual | **TalkBack** (Android) e **VoiceOver** (iPhone) no celular real | Toda tela nova |
| Manual | Zoom 400%, largura 320px, alto contraste do Windows | Toda tela nova |
| **Usabilidade** | Sessões com Cláudio, Andrey, Matheus, Lindaura (tarefas reais: "descubra quem é seu próximo atendimento") + 3 a 5 colaboradores | Fim de cada fase |

> Ferramentas automáticas pegam ~30 a 40% dos problemas. O teste com os massoterapeutas é obrigatório.

Métricas de sucesso (ligadas ao discovery): massoterapeuta completa "saber o próximo atendimento" sozinho em < 10s; taxa de no-show medida e caindo; zero conflitos de horário; % de agendamentos feitos sem a Silvana.

---

## 8. Decisões em aberto (confirmar antes da Fase 1)

1. **Hospedagem**: servidor/nuvem da empresa? (precisa de HTTPS para PWA e push)
2. **Login**: a migração para Google Workspace já vale para todos (inclusive massoterapeutas, que não têm conta corporativa)?
3. **Duração da sessão**: 15 ou 20 min? Tem intervalo entre sessões? (11 atend. em 440 min sugere ~40 min por ciclo)
4. ~~**Quem edita a disponibilidade**~~: decidido em 07/10/2026. O próprio massoterapeuta, na tela Meus horários.
5. **Política do benefício** (tolerância 5 min, cancelamento 15 min, falta conta no limite): aprovada pelo RH?
6. **Celulares dos massoterapeutas**: quais modelos/sistemas (Android × iPhone)? Define prioridades de teste e se vibração funciona.
7. **Canal extra de lembrete**: só push, ou também e-mail/Teams/Google Chat?
8. **LGPD**: dados de saúde/deficiência no perfil → guardar só as preferências de interface (não o diagnóstico), com consentimento.

---

## 9. Próximos passos imediatos

1. Responder a seção 8
2. `git init`, criar projeto Django com a estrutura da seção 4.2
3. Implementar `base.html` + tokens/temas + componentes, com teste axe no CI
4. Protótipo das telas "Agora" (massoterapeuta) e "Agendar" (colaborador) → testar com o Cláudio

---

## 10. Andamento

**30/09/2026: esqueleto da Fase 1 criado** (ver [README.md](README.md))

Feito:
- Projeto Django 5.2 com apps `contas` e `agenda`, SQLite local, dados de demonstração (`popular_demo`)
- Paleta DT-WBS em tokens, com 5 temas (sistema, claro, escuro, alto contraste escuro e claro), texto de 100% a 250%, letra de alta legibilidade, espaçamento ampliado, modo simplificado, redução de movimento
- Preferências por pessoa, com tela de primeiro acesso
- Colaborador: agendar em 3 passos (dia → horário → confirmar), "Vou / Não vou", "Cheguei", regras do benefício aplicadas
- Massoterapeuta: tela "Minha agenda" com próximo atendimento, atendido/faltou, pausa rápida, "Ouvir agenda de hoje", atualização automática com anúncio falado/vibração/bipe (novo agendamento, chegada, cancelamento, 5 min antes)
- Administrador: agenda do dia por massoterapeuta, cancelar qualquer agendamento, cadastros pelo admin
- 41 testes (regras + checagens de acessibilidade do HTML)

Próximo:
- Responder a seção 8 (principalmente duração da sessão e quem edita a disponibilidade)
- Testar com TalkBack/VoiceOver no celular real e com o axe-core (Playwright)
- Fase 2: service worker + Web Push, lembrete "vou / não vou"
- Encaixe manual pelo administrador fora do admin

**30/09/2026: Fase 2 (notificações e lembretes) concluída no código**

Feito:
- App `notificacoes`: Web Push com VAPID próprio (`pywebpush`, gratuito), histórico de avisos com proteção contra duplicidade, reenvio automático de falhas, remoção de aparelhos que saíram
- Service worker + PWA instalável (ícones PNG para Android/iPhone, página sem internet que não guarda dados pessoais)
- Massoterapeuta recebe: novo agendamento do dia, chegada, cancelamento do dia, "próximo em 5 minutos"; se a tela estiver aberta, o aviso vai direto para o leitor de tela/voz e a agenda atualiza na hora
- Colaborador recebe lembrete com botões **Vou / Não vou** (60 min antes, configurável; respeita o prazo de cancelamento) e aviso quando o administrador cancela
- Painel "Ativar notificações neste aparelho" em Preferências e nas telas principais, com instruções para iPhone (Tela de Início) e para permissão bloqueada
- Processador periódico sem Redis: `manage.py notificacoes --continuo` (ou agendado a cada minuto). O `django-q2` previsto no plano não foi necessário
- 66 testes no total

Falta validar:
- Entrega real no celular (Android e iPhone) via túnel HTTPS. Não é possível no navegador de desenvolvimento, que bloqueia notificações
- Como TalkBack e VoiceOver leem as notificações e os botões Vou / Não vou, com os massoterapeutas e colaboradores

**30/09/2026: Check-in antecipado com liberação automática**

Regra pedida: o check-in (confirmar que vai) tem prazo de **1 hora antes** da massagem; passados **5 minutos** sem check-in, a reserva fica disponível para outras pessoas.

Decisões tomadas na implementação (todas configuráveis no admin):
- O check-in **abre 2 h antes** (lembrete no celular nesse momento). Uma janela de só 5 minutos seria uma barreira para quem está em reunião ou usa leitor de tela (WCAG 2.2.1, limite de tempo). Para a janela literal de 5 min, use "check-in abre" = 60.
- **Último aviso** urgente no prazo (1 h antes), com botões Fazer check-in / Não vou.
- Reserva liberada **não conta** no limite semanal (a vaga foi reaproveitada); falta continua contando.
- Quem agenda com o check-in já aberto fica com check-in feito na hora.
- Horários que já passaram não são liberados.
- O antigo "check-in" na porta da sala virou **chegada** ("Cheguei"), para não confundir.

A confirmar com RH/administrador: se a reserva liberada deve contar no limite semanal. A abertura de 2 h foi aprovada em 07/10/2026.

**07/10/2026: tudo pela tela, lista de espera, painel e comunicados**

Feito:
- Tudo que antes exigia o admin agora tem tela própria, com as mesmas regras de acessibilidade:
  - Massoterapeuta edita os próprios horários semanais e marca folgas e férias (Meus horários). Se houver gente marcada no período, o site lista as pessoas e só cancela com confirmação, avisando cada uma.
  - Administrador agenda para qualquer pessoa, faz encaixe fora da grade (se a sessão inteira couber) e pode marcar uma exceção às regras do benefício, que fica registrada.
  - Administrador cadastra e edita pessoas (incluindo massoterapeutas, duração e intervalo da sessão) e as regras do benefício.
  - O admin do Django continua existindo só para o superusuário (unidades e correções raras).
- Lista de espera ("me avise se abrir vaga") por dia, com um massoterapeuta ou qualquer um. Quando alguém cancela ou uma reserva é liberada sem check-in, todos que esperam por aquele dia recebem um aviso; quem agendar primeiro fica com o horário.
- Histórico de alterações de cada agendamento (quem agendou, encaixou, fez check-in, cancelou, marcou falta). Foi feito com um modelo próprio em vez do `django-simple-history`, para mostrar o histórico em linguagem simples na tela do administrador e no painel.
- Painel do SESMT: ocupação, atendimentos, usuários únicos, faltas, cancelamentos, liberações e encaixes, por massoterapeuta e por semana, com tabela e exportação para CSV. O papel SESMT entra direto no painel.
- Página pública "Como funciona o benefício", com as regras da unidade.
- VLibras carregado sob demanda (link no rodapé) ou sempre, se a pessoa ligar nas preferências.
- Comunicados da empresa para massoterapeutas ou para todos, com aviso opcional no celular e marcação de "novo".
- `psycopg[binary]` adicionado para usar PostgreSQL.

