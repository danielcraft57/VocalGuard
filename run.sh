#!/usr/bin/env bash

# Démarrage VocalGuard (mode "single window"):
# - backend + celery en arrière-plan (logs/),
# - frontend au premier plan,
# - nettoyage automatique à l'arrêt (Ctrl+C).

set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${PROJECT_ROOT}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Démarrage de VocalGuard (single window)...${NC}"

USE_CONDA=false
CONDA_ENV_NAME="vocalguard"
PYTHON_CMD="python3"

if command -v conda >/dev/null 2>&1; then
  if conda env list | awk '{print $1}' | grep -qx "${CONDA_ENV_NAME}"; then
    USE_CONDA=true
    echo -e "${GREEN}Environnement conda '${CONDA_ENV_NAME}' détecté.${NC}"
  fi
fi

if [ "${USE_CONDA}" = true ]; then
  # shellcheck disable=SC1091
  eval "$(conda shell.bash hook)"
  conda activate "${CONDA_ENV_NAME}"
  PYTHON_CMD="python"
else
  if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Création de l'environnement virtuel...${NC}"
    python3 -m venv venv
  fi
  # shellcheck disable=SC1091
  source venv/bin/activate
  PYTHON_CMD="python"
fi

echo -e "${GREEN}Installation/MAJ dépendances Python...${NC}"
"${PYTHON_CMD}" -m pip install --upgrade pip >/dev/null
"${PYTHON_CMD}" -m pip install -r requirements.txt >/dev/null

mkdir -p logs audio_cache data
rm -f logs/*.log logs/*.err.log 2>/dev/null || true

if [ ! -f "config/config.yaml" ] && [ -f "config/config.example.yaml" ]; then
  echo -e "${YELLOW}Création config/config.yaml depuis config.example...${NC}"
  cp config/config.example.yaml config/config.yaml
fi

if [ ! -f "config/config.yaml" ]; then
  echo -e "${RED}config/config.yaml introuvable.${NC}"
  exit 1
fi

if [ ! -d "frontend" ]; then
  echo -e "${RED}Dossier frontend introuvable.${NC}"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo -e "${RED}npm introuvable. Installe Node.js pour lancer le frontend.${NC}"
  exit 1
fi

# Production helpers (.env.prod)
if [ "${VG_ENV:-dev}" = "prod" ]; then
  echo -e "${GREEN}Mode production détecté (VG_ENV=prod).${NC}"
fi

echo -e "${YELLOW}Nettoyage Redis Celery (si redis://)...${NC}"
"${PYTHON_CMD}" - <<'PY'
import os
from pathlib import Path
from urllib.parse import urlparse

def read_env(path: Path):
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

try:
    from redis import Redis
except Exception:
    raise SystemExit(0)

env_name = os.environ.get("VG_ENV", "dev").strip().lower()
root = Path(".")
env_file = root / f".env.{env_name}"
if not env_file.exists():
    env_file = root / ".env"
env_map = read_env(env_file)

broker = env_map.get("CELERY_BROKER_URL") or os.environ.get("CELERY_BROKER_URL") or "redis://localhost:6379/0"
backend = env_map.get("CELERY_RESULT_BACKEND") or os.environ.get("CELERY_RESULT_BACKEND") or broker

seen = set()
for url in (broker, backend):
    if not url or url in seen or not url.startswith("redis://"):
        continue
    seen.add(url)
    p = urlparse(url)
    db = 0
    if p.path and p.path != "/":
        try:
            db = int(p.path.lstrip("/"))
        except Exception:
            db = 0
    try:
        r = Redis(
            host=p.hostname or "localhost",
            port=p.port or 6379,
            db=db,
            username=p.username,
            password=p.password,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        r.ping()
        r.flushdb()
        print(f"[redis-cleanup] FLUSHDB ok -> {p.hostname}:{p.port or 6379}/{db}")
    except Exception as exc:
        print(f"[redis-cleanup] skip {url}: {exc}")
PY

backend_pid=""
celery_pid=""

cleanup() {
  echo -e "${YELLOW}Arrêt des processus backend/celery...${NC}"
  if [ -n "${backend_pid}" ] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  if [ -n "${celery_pid}" ] && kill -0 "${celery_pid}" 2>/dev/null; then
    kill "${celery_pid}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo -e "${GREEN}Lancement backend + celery en arrière-plan...${NC}"
"${PYTHON_CMD}" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2> logs/backend.err.log &
backend_pid=$!
"${PYTHON_CMD}" -m celery -A backend.celery_app.celery_app worker --loglevel=info --pool=solo > logs/celery.log 2> logs/celery.err.log &
celery_pid=$!

echo -e "${GREEN}Backend: http://localhost:8000${NC}"
echo -e "${GREEN}Frontend: http://localhost:3000${NC}"
echo -e "${YELLOW}Logs backend: logs/backend.log (err: logs/backend.err.log)${NC}"
echo -e "${YELLOW}Logs celery: logs/celery.log (err: logs/celery.err.log)${NC}"
echo -e "${YELLOW}Ctrl+C pour tout arrêter.${NC}"

cd frontend
exec npm run dev

