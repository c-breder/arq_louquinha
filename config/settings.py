import os
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# Variável vazia conta como não definida
def env(name, default=None):
    value = os.environ.get(name, "")
    return value if value != "" else default


def env_bool(name, default=False):
    value = env(name)
    return default if value is None else value.lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    return int(env(name, default))


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

DEV_DB_PASSWORD = "arq-dev-only"
SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY no .env.")
    SECRET_KEY = "dev-only-insecure-key"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

SITE_NAME = env("SITE_NAME", "Arquivo Louquinha")
ADMIN_URL = env("ADMIN_URL", "admin/")
SIGNUP_OPEN = env_bool("SIGNUP_OPEN", True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.postgres",
    "django.contrib.flatpages",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.mfa",
    "core",
    "accounts",
    "tags",
    "works",
    "interactions",
    "moderation",
    "challenges",
    "messaging",
]

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
if GOOGLE_CLIENT_ID:
    INSTALLED_APPS.append("allauth.socialaccount.providers.google")

MIDDLEWARE = [
    "core.middleware.CloudflareRealIPMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.UserLanguageMiddleware",
    "core.ratelimit.RateLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "core.middleware.ApprovalRequiredMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

# --- Banco ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "arq"),
        "USER": env("POSTGRES_USER", "arq"),
        "PASSWORD": env("POSTGRES_PASSWORD", DEV_DB_PASSWORD),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
if not DEBUG and DATABASES["default"]["PASSWORD"] == DEV_DB_PASSWORD:
    raise ImproperlyConfigured("Defina POSTGRES_PASSWORD no .env.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis: db 0 = fila do Celery, db 1 = cache ---
REDIS_URL = env("REDIS_URL", "redis://localhost:6379")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/1",
        "TIMEOUT": 300,
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"

# --- Celery ---
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_WORKER_CONCURRENCY = env_int("CELERY_CONCURRENCY", 1)
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_BEAT_SCHEDULE = {
    "publish-scheduled": {"task": "works.tasks.publish_scheduled", "schedule": 60.0},
    "cleanup-unused-images": {"task": "works.tasks.cleanup_unused_images", "schedule": crontab(hour=4, minute=0)},
    "rebuild-listings": {"task": "works.tasks.rebuild_all_listings", "schedule": crontab(hour=3, minute=30)},
    "flush-counters": {"task": "interactions.tasks.flush_counters", "schedule": 60.0},
}

# Redis db 2: acessos e kudos pendentes (gravados em lote pelo worker)
COUNTERS_REDIS_URL = f"{REDIS_URL}/2"
MESSAGES_PER_HOUR = env_int("MESSAGES_PER_HOUR", 20)
MAX_IMPORT_MB = env_int("MAX_IMPORT_MB", 20)
IMPORTS_PER_HOUR = env_int("IMPORTS_PER_HOUR", 10)
COMMENTS_PER_HOUR = env_int("COMMENTS_PER_HOUR", 60)

# --- Limite de pedidos por IP (por minuto) ---
RATE_LIMIT_ENABLED = env_bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_GLOBAL = env_int("RATE_LIMIT_GLOBAL", 300)
RATE_LIMIT_SEARCH = env_int("RATE_LIMIT_SEARCH", 60)
RATE_LIMIT_AUTOCOMPLETE = env_int("RATE_LIMIT_AUTOCOMPLETE", 120)

# Testes atualizam a listagem na hora em vez de mandar para o Celery
LISTING_REFRESH_SYNC = False

# --- Contas ---
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "home"

ACCOUNT_ADAPTER = "accounts.adapter.AccountAdapter"
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.SignupForm"
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = f"[{SITE_NAME}] "
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http" if DEBUG else "https"
# Bloqueio temporário após logins falhos (por IP e por conta)
ACCOUNT_RATE_LIMITS = {
    "login_failed": "10/m/ip,5/5m/key",
    "signup": "5/h/ip",
}

SOCIALACCOUNT_AUTO_SIGNUP = False  # obriga a passar pelo formulário (confirmação 18+)
SOCIALACCOUNT_PROVIDERS = {}
if GOOGLE_CLIENT_ID:
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": GOOGLE_CLIENT_ID, "secret": env("GOOGLE_CLIENT_SECRET", "")}],
        "SCOPE": ["profile", "email"],
    }

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = SITE_NAME

# --- E-mail ---
# Em dev os e-mails só aparecem no terminal
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{SITE_NAME} <nao-responda@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- Idioma: português nativo, inglês só por escolha ---
LANGUAGE_CODE = "pt-br"
LANGUAGES = [
    ("pt-br", "Português (Brasil)"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

# --- Arquivos ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Capítulos longos (o AO3 aceita ~500 mil caracteres)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# --- Imagens ---
MAX_IMAGE_UPLOAD_MB = env_int("MAX_IMAGE_UPLOAD_MB", 5)
IMAGE_QUOTA_MB = env_int("IMAGE_QUOTA_MB", 100)
IMAGE_MAX_WIDTH = env_int("IMAGE_MAX_WIDTH", 1600)
MAX_AVATAR_UPLOAD_MB = 2
AVATAR_SIZE = 256
UNUSED_IMAGE_DAYS = 7

# Conta que recebe as obras de quem exclui a conta e escolhe "deixar órfãs"
ORPHAN_USERNAME = "orphan_account"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
        )
    },
}

# --- Segurança ---
TRUST_CF_CONNECTING_IP = env_bool("TRUST_CF_CONNECTING_IP", False)
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
LANGUAGE_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    LANGUAGE_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
