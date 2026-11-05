#!/bin/bash
# Passe whisper-server de medium/small vers base (plus rapide, deja sur le Pi).
# Usage sur node15 : sudo bash /opt/vocalguard-stt/scripts/switch_whisper_base.sh
set -euo pipefail

ROOT="${STT_BASE_PATH:-/opt/vocalguard-stt}"
UNIT="/etc/systemd/system/vocalguard-whisper.service"
MODEL="ggml-base-q5_1.bin"
ENV_FILE="$ROOT/.env.stt"

if [ "$(id -u)" -ne 0 ]; then
  echo "Lancez avec sudo."
  exit 1
fi

if [ ! -f "$ROOT/whisper-models/$MODEL" ]; then
  echo "Modele manquant: $ROOT/whisper-models/$MODEL"
  exit 1
fi

sed -i "s|ggml-medium-q5_0.bin|$MODEL|g" "$UNIT"
sed -i "s|ggml-small-q5_1.bin|$MODEL|g" "$UNIT"
sed -i "s|STT_WHISPER_MODEL=medium|STT_WHISPER_MODEL=base|" "$ENV_FILE"
sed -i "s|STT_WHISPER_MODEL=small|STT_WHISPER_MODEL=base|" "$ENV_FILE"
sed -i "s|STT_WHISPER_CPP_MODEL=.*|STT_WHISPER_CPP_MODEL=$ROOT/whisper-models/$MODEL|" "$ENV_FILE"

systemctl daemon-reload
systemctl restart vocalguard-whisper
echo "Attente chargement modele base..."
sleep 12
systemctl restart vocalguard-stt
sleep 4
curl -s "http://127.0.0.1:8100/health" || true
echo ""
systemctl is-active vocalguard-whisper vocalguard-stt
grep ExecStart "$UNIT" || true
