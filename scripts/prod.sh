#!/bin/sh
# Atalho para o docker compose de produção: projeto "arq_prod", separado do dev (banco e volumes próprios).
# Exemplos: ./scripts/prod.sh ps | ./scripts/prod.sh logs -f web
set -eu
cd "$(dirname "$0")/.."

if [ ! -f .env.prod ]; then
    echo "Falta o .env.prod. Rode antes: ./scripts/init-env-prod.sh" >&2
    exit 1
fi

profiles="--profile prod"
# Túnel da Cloudflare só quando houver token
if grep -q '^CLOUDFLARE_TUNNEL_TOKEN=..*' .env.prod; then
    profiles="$profiles --profile tunnel"
fi

# No Git Bash (Windows), impede que "/scripts/x.sh" vire "C:/Program Files/Git/scripts/x.sh"
export MSYS_NO_PATHCONV=1
exec docker compose -p arq_prod --env-file .env.prod $profiles "$@"
