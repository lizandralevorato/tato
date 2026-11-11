"""Configurações do projeto Agenda de Massagem.

Valores sensíveis vêm de variáveis de ambiente (arquivo .env em desenvolvimento).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(nome, padrao=False):
    return os.getenv(nome, str(padrao)).strip().lower() in {"1", "true", "sim", "yes"}


def env_lista(nome, padrao=""):
    return [item.strip() for item in os.getenv(nome, padrao).split(",") if item.strip()]


CHAVE_DEV = "dev-inseguro-troque-em-producao"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or CHAVE_DEV
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
# Sem valor explícito, aceita HTTPS nos próprios hosts permitidos (evita 403 no login).
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS") or [
    f"https://{host.lstrip('.')}" for host in ALLOWED_HOSTS if host not in {"localhost", "127.0.0.1", "*"}
]

if not DEBUG and SECRET_KEY == CHAVE_DEV:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY em produção (DJANGO_DEBUG=0).")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.contas",
    "apps.agenda",
    "apps.ficha",
    "apps.notificacoes",
    "apps.comunicados",
    "apps.painel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.contas.context_processors.acessibilidade",
                "apps.notificacoes.context_processors.push",
                "apps.comunicados.context_processors.comunicados",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.getenv("DATABASE_URL"):
    # Formato entregue pelas hospedagens: postgres://usuario:senha@host:5432/banco
    import dj_database_url

    DATABASES = {"default": dj_database_url.config(conn_max_age=600, conn_health_checks=True)}
elif os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "contas.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "contas:entrar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "contas:entrar"

# Sessão longa: massoterapeutas usam o próprio celular e não devem precisar
# entrar de novo a cada turno (WCAG 2.2.1: sem limites de tempo inesperados).
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

from django.contrib.messages import constants as mensagens  # noqa: E402

MESSAGE_TAGS = {
    mensagens.DEBUG: "info",
    mensagens.INFO: "info",
    mensagens.SUCCESS: "sucesso",
    mensagens.WARNING: "aviso",
    mensagens.ERROR: "erro",
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True

# Erros e avisos vão para a saída padrão, que é o que as hospedagens mostram como log.
# (Sem isto, com DEBUG=False o Django só tentaria mandar os erros por e-mail.)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
    },
}

# Web Push (notificações). Gere com: python manage.py gerar_chaves_vapid
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CONTATO = os.getenv("VAPID_CONTATO", "mailto:administrador@suaempresa.com.br")
