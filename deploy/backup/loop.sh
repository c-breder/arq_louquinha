#!/bin/sh
# Agenda do container de backup: um backup por dia no horário BACKUP_TIME
set -u

# Primeiro backup logo ao subir, se ainda não houver nenhum
if [ -z "$(find /backups/daily -name COMPLETO 2>/dev/null)" ]; then
    /scripts/backup.sh || echo "Primeiro backup falhou."
fi

while true; do
    now=$(date +%s)
    target=$(date -d "$(date +%Y-%m-%d) ${BACKUP_TIME:-03:00}" +%s)
    [ "$target" -le "$now" ] && target=$((target + 86400))
    sleep $((target - now))
    /scripts/backup.sh || echo "Backup falhou em $(date)."
done
