#!/bin/bash
# Ajuste PostgreSQL pour Raspberry Pi ~1 Go RAM (sans toucher aux donnees).
# Usage: sudo bash scripts/postgres/tune_pi_memory.sh
set -euo pipefail

PG_VER="${PG_VER:-17}"
PG_CONF="/etc/postgresql/${PG_VER}/main/postgresql.conf"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Lancer en root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$PG_CONF" ]]; then
  echo "postgresql.conf introuvable: $PG_CONF" >&2
  exit 1
fi

apply_kv() {
  local key="$1"
  local val="$2"
  if grep -qE "^#?${key}[[:space:]]*=" "$PG_CONF"; then
    sed -i "s|^#\\?${key}[[:space:]]*=.*|${key} = ${val}|" "$PG_CONF"
  else
    echo "${key} = ${val}" >> "$PG_CONF"
  fi
}

# Pi 1 Go : moins de connexions idle + buffers plus bas (defaut install etait 128MB shared / 512MB cache)
apply_kv "max_connections" "25"
apply_kv "shared_buffers" "64MB"
apply_kv "effective_cache_size" "256MB"
apply_kv "work_mem" "2MB"
apply_kv "maintenance_work_mem" "32MB"
apply_kv "wal_buffers" "4MB"
apply_kv "max_wal_size" "256MB"

systemctl restart postgresql
echo "OK PostgreSQL ${PG_VER} tune Pi (max_connections=25 shared_buffers=64MB)"
