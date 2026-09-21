#!/usr/bin/env bash
# Installe la rotation journaliere des logs VocalGuard via logrotate (prod Pi).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
SERVICE_USER="${SERVICE_USER:-pi}"
SERVICE_GROUP="${SERVICE_GROUP:-pi}"
RETENTION_DAYS="${LOG_RETENTION_DAYS:-30}"
MAX_SIZE="${LOG_MAX_SIZE:-100M}"
TARGET="/etc/logrotate.d/vocalguard"
TEMPLATE="$APP_DIR/scripts/logrotate/vocalguard"

if ! command -v logrotate >/dev/null 2>&1; then
  echo "Installation du paquet logrotate..."
  export DEBIAN_FRONTEND=noninteractive
  sudo -E apt-get update -qq
  sudo -E apt-get install -y logrotate
fi

if [ ! -d "$APP_DIR/logs" ]; then
  mkdir -p "$APP_DIR/logs"
fi

# Genere la config finale (APP_DIR et retention configurables sur le Pi).
TMP_FILE="$(mktemp)"
sed \
  -e "s|^/opt/vocalguard|${APP_DIR}|" \
  -e "s|su pi pi|su ${SERVICE_USER} ${SERVICE_GROUP}|" \
  -e "s|rotate 30|rotate ${RETENTION_DAYS}|" \
  -e "s|maxsize 100M|maxsize ${MAX_SIZE}|" \
  "$TEMPLATE" >"$TMP_FILE"

sudo cp "$TMP_FILE" "$TARGET"
sudo chmod 644 "$TARGET"
rm -f "$TMP_FILE"

echo "Logrotate VocalGuard installe:"
echo "  cible: $TARGET"
echo "  logs:  ${APP_DIR}/logs/*.log"
echo "  daily, retention ${RETENTION_DAYS} jours, maxsize ${MAX_SIZE}, copytruncate"

# Dry-run pour valider la syntaxe (sortie tronquee).
sudo logrotate -d "$TARGET" 2>&1 | head -n 15 || true
