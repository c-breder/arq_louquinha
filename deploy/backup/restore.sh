#!/bin/sh
# Restaura banco e mídia de uma pasta de backup. Use pelo scripts/restore.sh (para o site antes).
set -eu

src="${1:?Uso: restore.sh /backups/daily/<pasta>}"
if [ ! -f "$src/COMPLETO" ]; then
    echo "Backup incompleto ou inexistente: $src" >&2
    exit 1
fi

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_restore -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner "$src/db.dump"
find /data/media -mindepth 1 -delete
tar -xzf "$src/media.tar.gz" -C /data/media
echo "Restaurado de $src."
