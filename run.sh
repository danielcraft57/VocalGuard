#!/bin/bash

# Script de démarrage pour VocalGuard

set -e

# Couleurs pour les messages
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Démarrage de VocalGuard...${NC}"

# Détecter et utiliser conda si disponible, sinon utiliser venv
USE_CONDA=false
CONDA_ENV_NAME="vocalguard"

# Vérifier si conda est disponible
if command -v conda &> /dev/null; then
    # Vérifier si l'environnement conda existe
    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        USE_CONDA=true
        echo -e "${GREEN}Environnement conda '${CONDA_ENV_NAME}' détecté${NC}"
    fi
fi

if [ "$USE_CONDA" = true ]; then
    # Activer l'environnement conda
    echo -e "${GREEN}Activation de l'environnement conda '${CONDA_ENV_NAME}'...${NC}"
    # Initialiser conda pour ce shell
    eval "$(conda shell.bash hook)"
    conda activate "${CONDA_ENV_NAME}"
    
    # Vérifier si les dépendances sont installées en testant l'import de loguru
    echo -e "${GREEN}Vérification des dépendances...${NC}"
    if ! python -c "import loguru" 2>/dev/null; then
        echo -e "${YELLOW}Installation des dépendances...${NC}"
        pip install --upgrade pip
        pip install -r requirements.txt
    else
        echo -e "${GREEN}Dépendances déjà installées${NC}"
    fi
else
    # Utiliser venv
    # Vérifier si l'environnement virtuel existe
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}Création de l'environnement virtuel...${NC}"
        python3 -m venv venv
    fi
    
    # Activer l'environnement virtuel
    echo -e "${GREEN}Activation de l'environnement virtuel...${NC}"
    source venv/bin/activate
    
    # Vérifier si les dépendances sont installées
    if [ ! -f "venv/.installed" ]; then
        echo -e "${YELLOW}Installation des dépendances...${NC}"
        pip install --upgrade pip
        pip install -r requirements.txt
        touch venv/.installed
    fi
fi

# Créer les dossiers nécessaires
mkdir -p logs audio_cache data

# Vérifier la configuration
if [ ! -f "config/config.yaml" ]; then
    echo -e "${YELLOW}Création du fichier de configuration...${NC}"
    cp config/config.example.yaml config/config.yaml
    echo -e "${YELLOW}Veuillez éditer config/config.yaml avant de continuer${NC}"
    exit 1
fi

# Lancer l'application
echo -e "${GREEN}Lancement de VocalGuard...${NC}"
python -m vocalguard.main

