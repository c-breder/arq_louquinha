#!/bin/sh
# Atualiza a produção sem perder dados: backup → código novo → imagens → migrations → reinício.
set -eu
cd "$(dirname "$0")/.."
PROD=./scripts/prod.sh

echo "1/5 Backup de segurança (se o banco já estiver no ar)..."
if $PROD ps --status running --services 2>/dev/null | grep -qx db; then
    $PROD run --rm -T backup /scripts/backup.sh
else
    echo "    banco ainda não está rodando; pulando (primeira instalação)."
fi

echo "2/5 Código novo..."
if [ -d .git ]; then
    git pull --ff-only
else
    echo "    sem git nesta pasta; usando os arquivos atuais."
fi

echo "3/5 Montando as imagens..."
$PROD build

echo "4/5 Migrations..."
$PROD up -d db redis
# Garante que a pasta de mídia pertence ao usuário do site (uid 1000)
$PROD run --rm -T --no-deps --user root --entrypoint "" web chown -R 1000:1000 /app/media
$PROD run --rm -T web python manage.py migrate --noinput

echo "5/5 Reiniciando os serviços..."
$PROD up -d --remove-orphans
# Templates podem ter mudado: descarta os cards guardados no cache
$PROD exec -T web python manage.py shell -c "from django.core.cache import cache; cache.clear()"
$PROD ps
echo "Pronto. Site em http://localhost:${HTTP_PORT:-8080}"
