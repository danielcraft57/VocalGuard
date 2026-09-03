#!/bin/bash
# Cutover SQLite -> PostgreSQL sur node14.
# Usage (root, depuis /opt/vocalguard):
#   sudo bash scripts/postgres/cutover_node14.sh
set -euo pipefail

ROOT="${VG_ROOT:-/opt/vocalguard}"
cd "$ROOT"

echo "==> Archive SQLite"
bash "$ROOT/scripts/postgres/archive_sqlite.sh" "$ROOT"

if [[ ! -f /root/vocalguard_pg_password.txt ]]; then
  echo "Mot de passe PG manquant. Lancer d'abord install_postgres_node14.sh" >&2
  exit 1
fi
VG_PASS="$(tr -d '\n\r' < /root/vocalguard_pg_password.txt)"
DB_URL="postgresql+psycopg2://vocalguard:${VG_PASS}@127.0.0.1:5432/vocalguard"

echo "==> Alembic upgrade head"
export DATABASE_URL="$DB_URL"
export PYTHONPATH="$ROOT"
if [[ -x "$ROOT/venv/bin/python" ]]; then
  "$ROOT/venv/bin/python" -m alembic upgrade head
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  "$ROOT/.venv/bin/python" -m alembic upgrade head
else
  python3 -m alembic upgrade head
fi

echo "==> Met a jour .env DATABASE_URL"
ENV_FILE="$ROOT/.env"
touch "$ENV_FILE"
if grep -qE '^(DATABASE_URL|database_url)=' "$ENV_FILE" 2>/dev/null; then
  # sed in-place : remplace les lignes DATABASE_URL / database_url
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DB_URL}|" "$ENV_FILE"
  sed -i "s|^database_url=.*|database_url=${DB_URL}|" "$ENV_FILE"
else
  printf '\nDATABASE_URL=%s\n' "$DB_URL" >> "$ENV_FILE"
fi
# Evite create_all runtime (Alembic est la source de verite)
if ! grep -q '^VG_DB_AUTOCREATE=' "$ENV_FILE" 2>/dev/null; then
  printf 'VG_DB_AUTOCREATE=0\n' >> "$ENV_FILE"
fi

chown pi:pi "$ENV_FILE" 2>/dev/null || true

echo "==> Restart services"
systemctl start vocalguard.service
systemctl start vocalguard-telephony.service || true
sleep 2
systemctl is-active vocalguard.service

echo "==> Smoke /health"
curl -sf "http://127.0.0.1:8000/health" || curl -sf "http://127.0.0.1:8000/api/health" || true
echo
echo "Cutover OK. Verifier UI http://node14.lan:8000/"
