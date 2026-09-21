#!/usr/bin/env bash
# Maintenance periodique des logs prod VocalGuard (rotation + nettoyage archives).
# Appele par la tache Celery backend.workers.maintenance_tasks.run_log_maintenance.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="${LOG_MAINTENANCE_LOG:-$LOG_DIR/log_maintenance.log}"
KEEP_ARCHIVE_DAYS="${KEEP_ARCHIVE_DAYS:-7}"

mkdir -p "$LOG_DIR"

{
  echo "[$(date -Iseconds)] log maintenance start (APP_DIR=$APP_DIR)"

  install_script="$APP_DIR/scripts/install_logrotate.sh"
  if [ -f "$install_script" ]; then
    APP_DIR="$APP_DIR" bash "$install_script"
  else
    echo "[$(date -Iseconds)] WARN: install_logrotate.sh absent"
  fi

  if [ -f /etc/logrotate.d/vocalguard ]; then
    set +e
    rotate_out="$(sudo logrotate -f /etc/logrotate.d/vocalguard 2>&1)"
    rotate_rc=$?
    set -e
    if [ "$rotate_rc" -eq 0 ]; then
      echo "[$(date -Iseconds)] logrotate -f OK"
    else
      echo "[$(date -Iseconds)] logrotate -f WARN rc=$rotate_rc (souvent deja rotate aujourd'hui)"
      if [ -n "$rotate_out" ]; then
        echo "$rotate_out"
      fi
    fi
  else
    echo "[$(date -Iseconds)] ERROR: /etc/logrotate.d/vocalguard absent"
    exit 1
  fi

  if [ -d "$LOG_DIR/archive" ]; then
    removed="$(find "$LOG_DIR/archive" -mindepth 1 -maxdepth 1 -type d -name 'pre-cleanup-*' -mtime "+$KEEP_ARCHIVE_DAYS" -print)"
    if [ -n "$removed" ]; then
      find "$LOG_DIR/archive" -mindepth 1 -maxdepth 1 -type d -name 'pre-cleanup-*' -mtime "+$KEEP_ARCHIVE_DAYS" -exec rm -rf {} +
      echo "[$(date -Iseconds)] archives pre-cleanup supprimees (> ${KEEP_ARCHIVE_DAYS}j)"
    fi
  fi

  echo "[$(date -Iseconds)] log maintenance done"
} >>"$LOG_FILE" 2>&1
