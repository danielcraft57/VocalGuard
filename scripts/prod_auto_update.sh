#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vocalguard}"
BRANCH="${BRANCH:-master}"
LOCK_FILE="${LOCK_FILE:-/tmp/vocalguard-auto-update.lock}"
LOG_FILE="${LOG_FILE:-$APP_DIR/logs/auto_update.log}"

mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "[$(date -Iseconds)] auto-update start (branch=$BRANCH, dir=$APP_DIR)"

  if [ ! -d "$APP_DIR/.git" ]; then
    echo "[$(date -Iseconds)] skip: $APP_DIR/.git missing (repo non git)."
    exit 0
  fi

  cd "$APP_DIR"

  # Empêche les exécutions concurrentes (cron + action GitHub).
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "[$(date -Iseconds)] skip: another update is running."
    exit 0
  fi

  git fetch origin "$BRANCH"

  LOCAL_SHA="$(git rev-parse HEAD)"
  REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"
  if [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
    echo "[$(date -Iseconds)] up-to-date."
    exit 0
  fi

  # Garde-fou: ne pas écraser des modifs locales accidentelles.
  if [ -n "$(git status --porcelain)" ]; then
    echo "[$(date -Iseconds)] skip: working tree dirty, manual action required."
    exit 1
  fi

  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"

  if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
  fi

  python -m compileall backend -q || true

  sudo systemctl restart vocalguard
  sudo systemctl restart vocalguard-celery
  if systemctl is-enabled vocalguard-frontend >/dev/null 2>&1; then
    sudo systemctl restart vocalguard-frontend
  fi

  curl -fsS "http://127.0.0.1:8000/health" >/dev/null
  echo "[$(date -Iseconds)] deploy complete: $LOCAL_SHA -> $REMOTE_SHA"
} >>"$LOG_FILE" 2>&1
