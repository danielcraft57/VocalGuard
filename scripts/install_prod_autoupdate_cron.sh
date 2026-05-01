#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
BRANCH="${BRANCH:-master}"
SCHEDULE="${SCHEDULE:-*/5 * * * *}"
SCRIPT_PATH="$APP_DIR/scripts/prod_auto_update.sh"

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Script non trouvé: $SCRIPT_PATH"
  exit 1
fi

chmod +x "$SCRIPT_PATH"

CRON_CMD="APP_DIR=$APP_DIR BRANCH=$BRANCH bash $SCRIPT_PATH"
CRON_LINE="$SCHEDULE $CRON_CMD"

TMP_FILE="$(mktemp)"
crontab -l 2>/dev/null | grep -v "prod_auto_update.sh" >"$TMP_FILE" || true
echo "$CRON_LINE" >>"$TMP_FILE"
crontab "$TMP_FILE"
rm -f "$TMP_FILE"

echo "Cron installé:"
echo "  $CRON_LINE"
echo "Vérifier: crontab -l"
