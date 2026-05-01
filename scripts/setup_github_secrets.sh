#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI requis (https://cli.github.com/)."
  exit 1
fi

echo "Configuration des secrets GitHub (optionnels, mails custom)."
echo "Laisser vide pour ignorer un secret."

read -r -p "SMTP_SERVER: " SMTP_SERVER
read -r -p "SMTP_USERNAME: " SMTP_USERNAME
read -r -s -p "SMTP_PASSWORD: " SMTP_PASSWORD
echo
read -r -p "ALERT_EMAIL_TO: " ALERT_EMAIL_TO
read -r -p "ALERT_EMAIL_FROM (optionnel): " ALERT_EMAIL_FROM

set_secret() {
  local name="$1"
  local value="$2"
  if [ -n "$value" ]; then
    printf "%s" "$value" | gh secret set "$name" --body -
    echo "Secret $name configuré."
  fi
}

set_secret "SMTP_SERVER" "$SMTP_SERVER"
set_secret "SMTP_USERNAME" "$SMTP_USERNAME"
set_secret "SMTP_PASSWORD" "$SMTP_PASSWORD"
set_secret "ALERT_EMAIL_TO" "$ALERT_EMAIL_TO"
set_secret "ALERT_EMAIL_FROM" "$ALERT_EMAIL_FROM"

echo "Terminé."
