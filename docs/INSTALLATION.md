# Guide d'installation VocalGuard

## Prérequis

### Matériel

- Raspberry Pi 3B+ ou mieux (ou système Linux compatible)
- Modem USB compatible :
  - US Robotics 5637 (recommandé)
  - Zoom 3095
  - Autres modems Conexant

### Logiciel

- Python 3.9 ou supérieur (3.13 recommandé)
- pip (gestionnaire de paquets Python)
- ffmpeg (pour le traitement audio)

## Installation

### 1. Installation des dépendances système

Sur Debian/Ubuntu/Raspberry Pi OS :

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv portaudio19-dev libasound2-dev ffmpeg
```

### 2. Cloner ou créer le projet

```bash
cd ~
mkdir vocalguard
cd vocalguard
```

### 3. Créer un environnement virtuel

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Installer les dépendances Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configuration

Copier le fichier de configuration exemple :

```bash
cp config/config.example.yaml config/config.yaml
```

Éditer la configuration selon vos besoins :

```bash
nano config/config.yaml
```

Principales options à configurer :

- `modem_port` : Port du modem (laisser `null` pour auto-détection)
- `voice_language` : Langue pour la reconnaissance/synthèse vocale (`fr`, `en`, etc.)
- `whisper_model` : Modèle Whisper à utiliser (`tiny`, `base`, `small`, `medium`, `large`)

### 6. Télécharger les modèles vocaux (optionnel)

#### Pour Whisper

Les modèles Whisper sont téléchargés automatiquement au premier usage.

#### Pour VOSK

Télécharger un modèle VOSK depuis https://alphacephei.com/vosk/models

```bash
mkdir -p ~/vosk-models
cd ~/vosk-models
wget https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip
unzip vosk-model-fr-0.22.zip
```

Mettre à jour `config.yaml` :

```yaml
vosk_model_path: "/home/pi/vosk-models/vosk-model-fr-0.22"
```

### 7. Créer les dossiers nécessaires

```bash
mkdir -p logs audio_cache data
```

### 8. Tester l'installation

```bash
python -m vocalguard.main
```

Vous devriez voir des messages de démarrage et la détection du modem.

## Installation avec Docker

### 1. Construire l'image

```bash
docker build -t vocalguard .
```

### 2. Lancer avec docker-compose

```bash
docker-compose up -d
```

### 3. Vérifier les logs

```bash
docker-compose logs -f
```

## Dépannage

### Le modem n'est pas détecté

1. Vérifier que le modem est branché : `lsusb`
2. Vérifier les ports série : `ls -l /dev/ttyACM* /dev/ttyUSB*`
3. Vérifier les permissions : `sudo usermod -a -G dialout $USER` puis redémarrer

### Erreurs audio

1. Vérifier que `portaudio19-dev` est installé
2. Vérifier que `pyaudio` est installé : `pip install pyaudio`

### Erreurs Whisper

1. Vérifier que `ffmpeg` est installé
2. Pour utiliser le GPU : installer `torch` avec support CUDA

### Erreurs de base de données

1. Vérifier les permissions d'écriture dans le dossier de données
2. Vérifier que SQLite est installé : `sudo apt-get install sqlite3`

## Prochaines étapes

- Consulter la [documentation de l'API](API.md)
- Configurer les règles de blocage
- Personnaliser les messages vocaux

