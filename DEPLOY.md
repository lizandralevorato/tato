# Publicar o TATO (Docker)

O projeto vira uma **imagem Docker**: o mesmo pacote roda no seu computador e em qualquer
hospedagem que aceite Docker (Railway, Render, Fly.io, um servidor próprio…).

## As peças

| Arquivo | Para que serve |
|---|---|
| `Dockerfile` | Receita da imagem: Python, dependências, arquivos estáticos e o servidor `gunicorn` |
| `.dockerignore` | O que fica fora da imagem (`.env`, `db.sqlite3`, testes, `.venv`…) |
| `docker-compose.yml` | Sobe localmente o site, o processador de notificações e um PostgreSQL |

A aplicação tem **dois processos**, os dois usando a mesma imagem:

1. **Site**: o comando padrão da imagem. Aplica as migrações e sobe o `gunicorn`.
2. **Notificações**: `python manage.py notificacoes --continuo`. Envia lembretes, libera
   reservas sem check-in e reenvia falhas, a cada minuto.

E precisa de um **PostgreSQL**. O SQLite não serve em hospedagem: o disco do container
é apagado a cada deploy, e o banco iria junto.

## Testar no seu computador (opcional)

Precisa do [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado.

```bash
docker compose up --build
```

Abra http://localhost:8000. Para criar um administrador ou dados de exemplo, em outro terminal:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py popular_demo
```

Parar: `Ctrl+C`. Apagar também o banco de teste: `docker compose down -v`.

## Variáveis de ambiente na hospedagem

| Variável | Valor |
|---|---|
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | uma chave longa e aleatória (comando abaixo). **Nunca** a do `.env` local |
| `DJANGO_ALLOWED_HOSTS` | o endereço do site, sem `https://`. Ex.: `tato.up.railway.app,tato.suaempresa.com.br` |
| `DATABASE_URL` | entregue pela hospedagem ao criar o PostgreSQL (`postgres://…`) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CONTATO` | chaves das notificações (`manage.py gerar_chaves_vapid`) |

Opcionais: `DJANGO_CSRF_TRUSTED_ORIGINS` (se vazio, usa `https://` + cada host permitido),
`GUNICORN_WORKERS` (padrão 3), `DJANGO_SSL_REDIRECT` (padrão `1`), `DJANGO_LOG_LEVEL` (padrão `INFO`).
`PORT` é definida pela própria hospedagem.

Gerar a `DJANGO_SECRET_KEY`:

```bash
.venv/Scripts/python.exe -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

> **Chaves VAPID:** gere uma vez e não troque mais. Se mudarem, todos os celulares
> inscritos param de receber notificações e precisam ativar de novo.

O site **se recusa a subir** com `DJANGO_DEBUG=0` e sem `DJANGO_SECRET_KEY`. É de propósito.

## Passo a passo genérico

1. Suba o código para um repositório no GitHub (privado).
2. Na hospedagem, crie um projeto a partir desse repositório. Ela detecta o `Dockerfile`.
3. Crie um **PostgreSQL** no mesmo projeto e copie a `DATABASE_URL` dele.
4. Configure as variáveis acima no serviço do site.
5. Crie um **segundo serviço** a partir do mesmo repositório, com as mesmas variáveis e o
   comando `python manage.py notificacoes --continuo` (sem porta pública).
6. Faça o deploy. Depois, no terminal/shell do serviço do site:
   `python manage.py createsuperuser`.
7. Abra o endereço gerado (`https://…`) e teste o login.
8. (Opcional) Domínio próprio: adicione o domínio no painel da hospedagem, crie o registro
   DNS (`CNAME`) que ela indicar e inclua o domínio em `DJANGO_ALLOWED_HOSTS`.
9. Gere o QR code com o endereço **final** (de preferência o domínio próprio).

## Antes de publicar

- O site guarda fichas do SESMT e dados de colaboradores (LGPD). Confirme com a TI ou o
  jurídico se a hospedagem escolhida é permitida.
- Não rode `popular_demo` em produção: ele cria contas fictícias com senha conhecida.
