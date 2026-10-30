#!/bin/sh
# Restaura um backup: para o site, restaura banco + mídia e sobe de novo.
# Uso: ./scripts/restore.sh daily/2026-10-30_030000   (pasta dentro de backups/)
set -eu
cd "$(dirname "$0")/.."
PROD=./scripts/prod.sh

name="${1:-}"
if [ -z "$name" ]; then
    echo "Uso: $0 <pasta do backup>. Disponíveis:"
    ls -1d backups/daily/*/ backups/weekly/*/ 2>/dev/null | sed 's|^backups/||; s|/$||'
    exit 1
fi

echo "Isso SUBSTITUI o banco e a mídia atuais pelo backup '$name'."
if [ "${CONFIRM:-}" != "sim" ]; then
    printf "Digite 'sim' para continuar: "
    read -r answer
    [ "$answer" = "sim" ] || { echo "Cancelado."; exit 1; }
fi

$PROD stop web worker caddy
$PROD run --rm -T backup /scripts/restore.sh "/backups/$name"
$PROD run --rm -T --no-deps --user root --entrypoint "" web chown -R 1000:1000 /app/media
$PROD up -d
$PROD exec -T web python manage.py rebuild_listings
echo "Restauração concluída."
