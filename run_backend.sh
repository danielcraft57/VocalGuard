#!/bin/bash
# Lance le backend VocalGuard (depuis la racine du projet).
# Utilise PYTHONPATH pour que le module backend soit trouve.

set -e
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)"
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
