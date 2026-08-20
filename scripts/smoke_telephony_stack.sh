#!/usr/bin/env bash
# Smoke tests stack API + telephony (a lancer sur node14 ou depuis SSH).
# Usage: bash scripts/smoke_telephony_stack.sh [/opt/vocalguard]
# Depuis Windows / CI sans bash : python scripts/test_api_stack.py (memes checks HTTP de base).
set -euo pipefail
ROOT="${1:-/opt/vocalguard}"
cd "$ROOT"
if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi
API="${TELEPHONY_PUBLIC_API_URL:-http://127.0.0.1:8000}"
TEL="${TELEPHONY_DAEMON_URL:-http://127.0.0.1:8090}"
TOK="${TELEPHONY_INTERNAL_TOKEN:-}"

echo "== GET $API/health =="
curl -fsS "$API/health" | head -c 300
echo ""

if curl -fsS --connect-timeout 2 "$TEL/health" >/dev/null 2>&1; then
  echo "== GET $TEL/health =="
  curl -fsS "$TEL/health" | head -c 300
  echo ""
else
  echo "!! Telephony daemon injoignable ($TEL) — normal si USE_TELEPHONY_DAEMON=0"
fi

if [[ -n "$TOK" ]]; then
  echo "== POST $API/api/v1/internal/telephony-events (attendu 202) =="
  code=$(curl -sS -o /tmp/vg_tel_ev.json -w "%{http_code}" -X POST "$API/api/v1/internal/telephony-events" \
    -H "Content-Type: application/json" \
    -H "X-VocalGuard-Internal: $TOK" \
    -d '{"event_type":"call.session.log","timestamp":"2026-05-02T12:00:00Z","data":{"call_id":1,"phone_number":"000","message":"smoke_telephony_stack","level":"info"},"source":"SmokeScript"}')
  echo "HTTP $code"
  cat /tmp/vg_tel_ev.json
  echo ""
  [[ "$code" == "202" ]] || { echo "ECHEC: attendu 202 (verifier TELEPHONY_INTERNAL_TOKEN)"; exit 1; }
else
  echo "!! TELEPHONY_INTERNAL_TOKEN vide — skip test relais interne"
fi

echo "== pytest telephony (sans modem) =="
source venv/bin/activate
pytest backend/tests/test_telephony_pipeline.py backend/tests/telephony_daemon -q

echo "OK smoke_telephony_stack"
