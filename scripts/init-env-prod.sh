#!/bin/sh
# Cria o .env.prod com senhas aleatórias. Não sobrescreve um existente.
set -eu
cd "$(dirname "$0")/.."

if [ -f .env.prod ]; then
    echo ".env.prod já existe; nada foi alterado."
    exit 0
fi

random() {
    head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c "$1"
}

cat > .env.prod <<EOF
# Produção. Nunca vai para o git. Veja o .env.example para todas as opções.
APP_ENV_FILE=.env.prod
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$(random 60)
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
# Com domínio: DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,meudominio.com.br
#              DJANGO_CSRF_TRUSTED_ORIGINS=https://meudominio.com.br
DJANGO_CSRF_TRUSTED_ORIGINS=
SITE_NAME=Arquivo Louquinha
ADMIN_URL=admin/

POSTGRES_DB=arq
POSTGRES_USER=arq
POSTGRES_PASSWORD=$(random 32)

# Acesso só local (http://localhost:8080) por enquanto.
# Ao ligar o túnel (HTTPS): SESSION_COOKIE_SECURE=1 e TRUST_CF_CONNECTING_IP=1
SESSION_COOKIE_SECURE=0
TRUST_CF_CONNECTING_IP=1
CLOUDFLARE_TUNNEL_TOKEN=

# E-mail: enquanto não houver provedor, os e-mails só aparecem no log (docker logs)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=arq_louquinha <nao-responda@localhost>

# Backups (pasta no PC; cópia externa opcional)
BACKUP_TIME=03:00
BACKUP_DIR=./backups
BACKUP_COPY_ENABLED=0
BACKUP_COPY_DIR=./backups-copia
RCLONE_REMOTE=

HTTP_PORT=8080
GUNICORN_WORKERS=2
CELERY_CONCURRENCY=1
EOF
chmod 600 .env.prod
echo ".env.prod criado com senhas aleatórias."
