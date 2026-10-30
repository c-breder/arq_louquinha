#!/bin/sh
# Backup: banco (pg_dump) + mídia. Guarda 7 diários e 4 semanais.
set -eu

stamp=$(date +%Y-%m-%d_%H%M%S)
dir="/backups/daily/$stamp"
mkdir -p "$dir" /backups/weekly

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$dir/db.dump"
tar -czf "$dir/media.tar.gz" -C /data/media .
date -Iseconds > "$dir/COMPLETO"  # marca de backup terminado

# Semanal: aos domingos, ou se não houver nenhum nos últimos 6 dias
if [ "$(date +%u)" = 7 ] || [ -z "$(find /backups/weekly -mindepth 1 -maxdepth 1 -mtime -6)" ]; then
    cp -r "$dir" "/backups/weekly/$stamp"
fi

# Rotação: apaga os mais antigos além do limite
keep() {
    ls -1d "$1"/*/ 2>/dev/null | sort -r | tail -n +"$(($2 + 1))" | xargs -r rm -rf
}
keep /backups/daily "${BACKUP_KEEP_DAILY:-7}"
keep /backups/weekly "${BACKUP_KEEP_WEEKLY:-4}"

# Cópia para fora da máquina (HD externo e/ou nuvem via rclone)
if [ "${BACKUP_COPY_ENABLED:-0}" = 1 ]; then
    rclone sync /backups /copy
fi
if [ -n "${RCLONE_REMOTE:-}" ]; then
    rclone --config /config/rclone/rclone.conf sync /backups "$RCLONE_REMOTE"
fi

echo "Backup $stamp concluído ($(du -sh "$dir" | cut -f1))."
