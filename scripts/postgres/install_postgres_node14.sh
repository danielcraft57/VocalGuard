#!/bin/bash
# Configure PostgreSQL 17 sur node14 pour VocalGuard (LAN + role + tuning Pi).
# Usage: sudo bash scripts/postgres/install_postgres_node14.sh [password]
set -euo pipefail

PG_VER="${PG_VER:-17}"
PG_CONF="/etc/postgresql/${PG_VER}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VER}/main/pg_hba.conf"
DB_USER="${DB_USER:-vocalguard}"
DB_NAME="${DB_NAME:-vocalguard}"
LAN_CIDR="${LAN_CIDR:-192.168.1.0/24}"
LAN_IP="${LAN_IP:-}"
VG_PASS="${1:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Lancer en root: sudo bash $0" >&2
  exit 1
fi

if [[ -z "$LAN_IP" ]]; then
  LAN_IP="$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | head -1)"
fi
if [[ -z "$LAN_IP" ]]; then
  echo "IP LAN introuvable" >&2
  exit 1
fi

if [[ -z "$VG_PASS" ]]; then
  VG_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 28)"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y postgresql postgresql-contrib

# Role + DB (recree vide pour schema neuf)
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${VG_PASS}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${VG_PASS}';
  END IF;
END
\$\$;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS ${DB_NAME};
CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

# Extensions dans la DB
sudo -u postgres psql -d "${DB_NAME}" -v ON_ERROR_STOP=1 <<SQL
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${DB_USER};
SQL

# postgresql.conf
sed -i "s/^#\\?listen_addresses.*/listen_addresses = 'localhost,${LAN_IP}'/" "$PG_CONF"
sed -i "s/^#\\?max_connections.*/max_connections = 40/" "$PG_CONF"
sed -i "s/^#\\?shared_buffers.*/shared_buffers = 128MB/" "$PG_CONF"
sed -i "s/^#\\?effective_cache_size.*/effective_cache_size = 512MB/" "$PG_CONF"
sed -i "s/^#\\?work_mem.*/work_mem = 4MB/" "$PG_CONF"
sed -i "s/^#\\?maintenance_work_mem.*/maintenance_work_mem = 64MB/" "$PG_CONF"
sed -i "s/^#\\?password_encryption.*/password_encryption = scram-sha-256/" "$PG_CONF"
if grep -q "^shared_preload_libraries" "$PG_CONF"; then
  sed -i "s|^shared_preload_libraries.*|shared_preload_libraries = 'pg_stat_statements'|" "$PG_CONF"
else
  echo "shared_preload_libraries = 'pg_stat_statements'" >> "$PG_CONF"
fi
grep -q "pg_stat_statements.track" "$PG_CONF" || echo "pg_stat_statements.track = all" >> "$PG_CONF"

# pg_hba.conf : local + LAN
cp -a "$PG_HBA" "${PG_HBA}.bak.$(date +%Y%m%d%H%M%S)"
cat > "$PG_HBA" <<EOF
# VocalGuard node14 - genere par install_postgres_node14.sh
local   all             postgres                                peer
local   all             all                                     scram-sha-256
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
host    all             ${DB_USER}      ${LAN_CIDR}             scram-sha-256
host    all             all             0.0.0.0/0               reject
host    all             all             ::/0                    reject
EOF

systemctl restart postgresql

# Firewall (si ufw present)
if command -v ufw >/dev/null 2>&1; then
  ufw allow from "${LAN_CIDR}" to any port 5432 proto tcp || true
fi

echo "OK PostgreSQL ${PG_VER}"
echo "LAN_IP=${LAN_IP}"
echo "DATABASE_URL=postgresql+psycopg2://${DB_USER}:${VG_PASS}@127.0.0.1:5432/${DB_NAME}"
echo "LAN_URL=postgresql+psycopg2://${DB_USER}:${VG_PASS}@${LAN_IP}:5432/${DB_NAME}"
# Ecrire un fichier root-only pour le deploy
umask 077
printf '%s\n' "$VG_PASS" > /root/vocalguard_pg_password.txt
chmod 600 /root/vocalguard_pg_password.txt
echo "Mot de passe aussi dans /root/vocalguard_pg_password.txt"
