# Imagem de produção do TATO (Django + gunicorn).
# A mesma imagem serve para o site e para o processador de notificações:
#   site:          comando padrão (abaixo)
#   notificações:  python manage.py notificacoes --continuo
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: só reinstala quando o requirements.txt muda.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Junta CSS/JS/imagens em staticfiles/ (servidos pelo WhiteNoise).
# A chave aqui é descartável: só existe durante o build.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=somente-para-o-build python manage.py collectstatic --noinput

# Não roda como root.
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# Aplica migrações e sobe o site. PORT é definida pela hospedagem (padrão 8000).
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-3} --timeout 60 --access-logfile -"]
