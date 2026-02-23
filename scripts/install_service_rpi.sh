#!/bin/bash
# Installe le service systemd VocalGuard sur le Raspberry Pi.
# A lancer sur le RPi, depuis ~/VocalGuard (apres deploiement).

set -e
SERVICE_NAME="vocalguard.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Adapter WorkingDirectory et User si besoin (par defaut /home/pi/VocalGuard)
VOCALGUARD_DIR="${VOCALGUARD_DIR:-$HOME/VocalGuard}"
SERVICE_USER="${SUDO_USER:-$USER}"

if [ ! -f "$PROJECT_DIR/vocalguard.service" ]; then
    echo "Erreur: vocalguard.service introuvable dans $PROJECT_DIR"
    exit 1
fi

# Creer une copie du service avec le bon repertoire
sed -e "s|/home/pi/VocalGuard|$VOCALGUARD_DIR|g" \
    -e "s|User=pi|User=$SERVICE_USER|g" \
    -e "s|Group=pi|Group=$SERVICE_USER|g" \
    "$PROJECT_DIR/vocalguard.service" > /tmp/vocalguard.service

echo "Installation du service dans /etc/systemd/system/"
sudo cp /tmp/vocalguard.service /etc/systemd/system/$SERVICE_NAME
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
echo "Service active au demarrage. Pour demarrer maintenant :"
echo "  sudo systemctl start $SERVICE_NAME"
echo "Pour voir les logs :"
echo "  journalctl -u $SERVICE_NAME -f"
