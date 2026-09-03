#!/bin/bash
set -euo pipefail
PASS="$(sudo cat /root/vocalguard_pg_password.txt | tr -d '\n\r')"
URL="postgresql+psycopg2://vocalguard:${PASS}@127.0.0.1:5432/vocalguard"
for f in /opt/vocalguard/.env /opt/vocalguard/.env.prod; do
  if [[ -f "$f" ]]; then
    if grep -qE '^(DATABASE_URL|database_url)=' "$f"; then
      sudo sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${URL}|" "$f"
      sudo sed -i "s|^database_url=.*|database_url=${URL}|" "$f"
    else
      printf '\nDATABASE_URL=%s\n' "$URL" | sudo tee -a "$f" >/dev/null
    fi
    if ! grep -q '^VG_DB_AUTOCREATE=' "$f"; then
      printf 'VG_DB_AUTOCREATE=0\n' | sudo tee -a "$f" >/dev/null
    fi
  fi
done
sudo chown pi:pi /opt/vocalguard/.env /opt/vocalguard/.env.prod 2>/dev/null || true
grep -E '^DATABASE_URL=' /opt/vocalguard/.env /opt/vocalguard/.env.prod | sed 's/:[^@]*@/:***@/g'
curl -sf -m 10 'http://127.0.0.1:8000/api/v1/calls?limit=1' >/dev/null
echo 'api_ok'
