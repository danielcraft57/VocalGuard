#!/usr/bin/env bash
# Legacy: redirige vers install_prod_log_maintenance_celery.sh (Celery Beat).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
TARGET="$APP_DIR/scripts/install_prod_log_maintenance_celery.sh"

echo "WARN: install_prod_log_maintenance_cron.sh est deprecie (Celery Beat)."
if [ -f "$TARGET" ]; then
  APP_DIR="$APP_DIR" bash "$TARGET"
else
  echo "Script absent: $TARGET"
  exit 1
fi
