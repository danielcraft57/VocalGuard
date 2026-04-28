#!/bin/bash
# Script de déploiement de VocalGuard sur Raspberry Pi
# Utilise RPI_HOST (ex: pi@raspberrypi.local) pour ne pas stocker d'hôte en dur.

set -e

# Configuration : préférer la variable d'environnement pour éviter les données personnelles dans le dépôt
RPI_HOST="${RPI_HOST:-pi@raspberrypi.local}"
RPI_DIR="~/VocalGuard"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=========================================="
echo "Déploiement de VocalGuard sur Raspberry Pi"
echo "Hôte: $RPI_HOST"
echo "=========================================="
echo ""

# Vérifier la connexion SSH
echo "[1/7] Vérification de la connexion SSH..."
if ! ssh -o ConnectTimeout=5 "$RPI_HOST" "echo 'Connexion OK'" > /dev/null 2>&1; then
    echo "❌ Impossible de se connecter à $RPI_HOST"
    echo "   Vérifiez que:"
    echo "   - Le Raspberry Pi est allumé"
    echo "   - SSH est activé"
    echo "   - La clé SSH est configurée (ou utilisez: ssh-copy-id $RPI_HOST)"
    exit 1
fi
echo "✅ Connexion SSH OK"
echo ""

# Supprimer et recréer le répertoire sur le RPi
echo "[2/7] Nettoyage et création du répertoire sur le Raspberry Pi..."
echo "   Suppression de l'ancien répertoire (s'il existe)..."
# Supprimer le contenu avec sudo si nécessaire, puis le dossier
ssh "$RPI_HOST" "sudo rm -rf $RPI_DIR/* $RPI_DIR/.* 2>/dev/null || true; rm -rf $RPI_DIR 2>/dev/null || true"
ssh "$RPI_HOST" "mkdir -p $RPI_DIR"
echo "✅ Répertoire créé: $RPI_DIR"
echo ""

# Vérifier Python
echo "[3/7] Vérification de Python..."
PYTHON_VERSION=$(ssh "$RPI_HOST" "python3 --version 2>&1 | head -1" || echo "")
if [ -z "$PYTHON_VERSION" ]; then
    echo "❌ Python3 n'est pas installé sur le Raspberry Pi"
    exit 1
fi
echo "✅ $PYTHON_VERSION détecté"
echo ""

# Vérifier pip
echo "[4/7] Vérification de pip..."
if ! ssh "$RPI_HOST" "python3 -m pip --version" > /dev/null 2>&1; then
    echo "⚠️ pip n'est pas installé, installation..."
    ssh "$RPI_HOST" "sudo apt-get update && sudo apt-get install -y python3-pip"
fi
echo "✅ pip disponible"
echo ""

# Créer l'environnement virtuel
echo "[5/7] Création de l'environnement virtuel..."
if ssh "$RPI_HOST" "[ ! -d $RPI_DIR/venv ]"; then
    ssh "$RPI_HOST" "cd $RPI_DIR && python3 -m venv venv"
    echo "✅ Environnement virtuel créé"
else
    echo "✅ Environnement virtuel existe déjà"
fi
echo ""

# Synchroniser les fichiers (excluant venv, __pycache__, etc.)
echo "[6/7] Synchronisation des fichiers..."
rsync -avz --progress \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.env' \
    --exclude '*.db' \
    --exclude '.git' \
    --exclude 'audio_cache' \
    --exclude 'logs' \
    --exclude 'data' \
    "$PROJECT_DIR/" "$RPI_HOST:$RPI_DIR/"
echo "✅ Fichiers synchronisés"
echo ""

# Installer les dépendances
echo "[7/7] Installation des dépendances..."
echo "   (Cela peut prendre plusieurs minutes...)"
ssh "$RPI_HOST" "cd $RPI_DIR && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
echo "✅ Dépendances installées"
echo ""

# Créer le fichier .env
echo "[8/8] Configuration de l'environnement..."
ssh "$RPI_HOST" "cd $RPI_DIR && if [ ! -f .env ]; then cp env.example .env; fi"

echo "✅ Configuration créée"
echo ""

echo "=========================================="
echo "✅ Déploiement terminé avec succès!"
echo "=========================================="
echo ""
echo "Pour tester le système:"
echo "  ssh $RPI_HOST"
echo "  cd $RPI_DIR"
echo "  source venv/bin/activate"
echo "  python scripts/test_patterns_voice.py"
echo ""
echo "Ou lancer VocalGuard complet:"
echo "  ./run_backend.sh"
echo "  (ou: PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0)"
echo ""
