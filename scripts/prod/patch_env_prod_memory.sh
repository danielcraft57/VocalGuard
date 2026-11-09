#!/bin/bash
# Patch .env prod (RAM / STT distant) sans ecraser secrets existants.
# Usage: bash scripts/prod/patch_env_prod_memory.sh [/opt/vocalguard]
set -euo pipefail

APP_DIR="${1:-/opt/vocalguard}"
ENV_FILE="${APP_DIR}/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo ".env absent: $ENV_FILE" >&2
  exit 1
fi

set_kv() {
  local key="$1"
  local val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

set_kv "VG_DB_POOL_SIZE" "5"
set_kv "VG_DB_MAX_OVERFLOW" "10"
set_kv "VG_ASYNCIO_POOL_WORKERS" "2"
set_kv "USE_TELEPHONY_DAEMON" "1"

if grep -q '^STT_SERVICE_URL=' "$ENV_FILE"; then
  set_kv "VG_STT_LOCAL" "0"
  sed -i '/^VOSK_MODEL_PATH=/d' "$ENV_FILE"
  sed -i '/^VOICE_RECOGNITION_ENGINE=vosk/d' "$ENV_FILE"
fi

if ! grep -q '^PROSPECT_PHONE_ENRICH_PARALLEL=' "$ENV_FILE"; then
  echo "PROSPECT_PHONE_ENRICH_PARALLEL=2" >> "$ENV_FILE"
fi

echo "OK patch .env memoire/STT ($ENV_FILE)"
