#!/bin/bash
# Applique migration perf indexes sur node14 (apres sync code).
set -euo pipefail
ROOT="${VG_ROOT:-/opt/vocalguard}"
cd "$ROOT"
PASS="$(sudo cat /root/vocalguard_pg_password.txt | tr -d '\n\r')"
export DATABASE_URL="postgresql+psycopg2://vocalguard:${PASS}@127.0.0.1:5432/vocalguard"
export PYTHONPATH="$ROOT"
"$ROOT/venv/bin/python" -m alembic upgrade head
systemctl restart vocalguard.service
systemctl restart vocalguard-telephony.service || true
sleep 3
curl -sf -m 15 http://127.0.0.1:8000/health >/dev/null
curl -sf -m 20 'http://127.0.0.1:8000/api/v1/stats' | head -c 120
echo
curl -sf -m 20 'http://127.0.0.1:8000/api/v1/calls?limit=5&with_osint=true' | head -c 120
echo
echo perf_ok
