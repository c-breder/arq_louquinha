#!/bin/sh
# Mostra a saúde da produção: serviços, RAM/CPU, banco, disco e backups.
set -eu
cd "$(dirname "$0")/.."
PROD=./scripts/prod.sh

echo "== Serviços"
$PROD ps --format "table {{.Service}}\t{{.Status}}"

echo
echo "== Memória e CPU"
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}" $($PROD ps -q)

echo
$PROD exec -T web python manage.py status

echo
echo "== Backups (pasta ${BACKUP_DIR:-./backups})"
du -sh backups 2>/dev/null || echo "nenhum ainda"
echo "Último diário: $(ls -1 backups/daily 2>/dev/null | sort | tail -n 1)"
echo "Semanais: $(ls -1 backups/weekly 2>/dev/null | wc -l)"
