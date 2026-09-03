#!/bin/bash
# Archive le SQLite VocalGuard avant cutover Postgres.
# Usage: sudo bash scripts/postgres/archive_sqlite.sh [/opt/vocalguard]
set -euo pipefail

ROOT="${1:-/opt/vocalguard}"
DB="${ROOT}/data/vocalguard.db"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/data/vocalguard.db.bak.${STAMP}"

if [[ ! -f "$DB" ]]; then
  echo "Pas de SQLite a archiver: $DB"
  exit 0
fi

# Stoppe les services qui tiennent le fichier ouvert si presents
systemctl stop vocalguard-telephony.service 2>/dev/null || true
systemctl stop vocalguard.service 2>/dev/null || true
sleep 1

cp -a "$DB" "$OUT"
gzip -f "$OUT"
echo "Archive: ${OUT}.gz"

# Ne supprime pas le .db original (rollback possible) — le deplacer a cote
mv "$DB" "${DB}.pre_postgres_${STAMP}"
echo "SQLite deplace: ${DB}.pre_postgres_${STAMP}"
