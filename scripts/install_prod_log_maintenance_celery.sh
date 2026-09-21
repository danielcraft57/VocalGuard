#!/usr/bin/env bash
# Retire le cron legacy et prepare la maintenance logs via Celery Beat (systemd).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"

TMP_FILE="$(mktemp)"
crontab -l 2>/dev/null | grep -v "prod_log_maintenance.sh" >"$TMP_FILE" || true
crontab "$TMP_FILE"
rm -f "$TMP_FILE"

if [ -f "$APP_DIR/scripts/install_logrotate.sh" ]; then
  chmod +x "$APP_DIR/scripts/install_logrotate.sh"
  APP_DIR="$APP_DIR" bash "$APP_DIR/scripts/install_logrotate.sh"
fi

if [ -f "$APP_DIR/scripts/prod_log_maintenance.sh" ]; then
  chmod +x "$APP_DIR/scripts/prod_log_maintenance.sh"
fi

echo "Cron prod_log_maintenance retire (si present)."
echo "Maintenance logs planifiee via Celery Beat (service vocalguard-celery-beat)."
echo "Verifier: systemctl status vocalguard-celery-beat"
echo "Tester:  cd $APP_DIR && source venv/bin/activate && python -m celery -A backend.celery_app.celery_app call backend.workers.maintenance_tasks.run_log_maintenance"
