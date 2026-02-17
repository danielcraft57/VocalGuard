#!/bin/bash

# Script d'installation des outils OSINT pour VocalGuard
# Compatible WSL/Kali Linux

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Installation des outils OSINT pour VocalGuard...${NC}"

# Vérifier si on est sur Linux/WSL
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${YELLOW}Attention: Ce script est conçu pour Linux/WSL${NC}"
    read -p "Continuer quand même? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Mettre à jour le système
echo -e "${GREEN}Mise à jour du système...${NC}"
sudo apt-get update

# Installer les dépendances de base
echo -e "${GREEN}Installation des dépendances...${NC}"
sudo apt-get install -y \
    golang-go \
    python3 \
    python3-pip \
    git \
    curl \
    wget

# Installer Go si nécessaire
if ! command -v go &> /dev/null; then
    echo -e "${GREEN}Installation de Go...${NC}"
    sudo apt-get install -y golang-go
fi

# Configurer Go PATH
if [ -d "$HOME/go" ]; then
    export PATH=$PATH:$HOME/go/bin
    echo 'export PATH=$PATH:$HOME/go/bin' >> ~/.bashrc
fi

# 1. Installer PhoneInfoga
echo -e "${GREEN}Installation de PhoneInfoga...${NC}"
if command -v phoneinfoga &> /dev/null; then
    echo -e "${YELLOW}PhoneInfoga est déjà installé${NC}"
else
    go install -v github.com/sundowndev/phoneinfoga/v2@latest
    if [ -f "$HOME/go/bin/phoneinfoga" ]; then
        echo -e "${GREEN}PhoneInfoga installé avec succès${NC}"
    else
        echo -e "${RED}Échec de l'installation de PhoneInfoga${NC}"
    fi
fi

# 2. Installer truecallerpy (optionnel)
echo -e "${GREEN}Installation de truecallerpy...${NC}"
pip3 install --user truecallerpy || echo -e "${YELLOW}truecallerpy non disponible ou déjà installé${NC}"

# 3. Installer theHarvester (optionnel)
echo -e "${GREEN}Installation de theHarvester...${NC}"
if command -v theHarvester &> /dev/null; then
    echo -e "${YELLOW}theHarvester est déjà installé${NC}"
else
    sudo apt-get install -y theharvester || echo -e "${YELLOW}theHarvester non disponible${NC}"
fi

# Vérifier les installations
echo -e "${GREEN}Vérification des installations...${NC}"

if command -v phoneinfoga &> /dev/null || [ -f "$HOME/go/bin/phoneinfoga" ]; then
    echo -e "${GREEN}✓ PhoneInfoga: Installé${NC}"
else
    echo -e "${RED}✗ PhoneInfoga: Non installé${NC}"
fi

if python3 -c "import truecallerpy" 2>/dev/null; then
    echo -e "${GREEN}✓ truecallerpy: Installé${NC}"
else
    echo -e "${YELLOW}✗ truecallerpy: Non installé (optionnel)${NC}"
fi

if command -v theHarvester &> /dev/null; then
    echo -e "${GREEN}✓ theHarvester: Installé${NC}"
else
    echo -e "${YELLOW}✗ theHarvester: Non installé (optionnel)${NC}"
fi

echo -e "${GREEN}Installation terminée!${NC}"
echo -e "${YELLOW}Note: Si vous utilisez WSL, vous devrez peut-être redémarrer votre terminal${NC}"
echo -e "${YELLOW}ou exécuter: source ~/.bashrc${NC}"

