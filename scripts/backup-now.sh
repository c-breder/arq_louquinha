#!/bin/sh
# Faz um backup agora (além do automático diário).
set -eu
cd "$(dirname "$0")/.."
./scripts/prod.sh run --rm -T backup /scripts/backup.sh
