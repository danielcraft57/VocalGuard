# Guide d'installation VocalGuard

## Prérequis

### Matériel

- Raspberry Pi 3B+ ou mieux (ou système Linux compatible)
- Modem USB compatible :
  - US Robotics 5637 (recommandé)
  - Zoom 3095
  - Autres modems Conexant

### Logiciel

- Python 3.9 ou supérieur (3.11+ recommandé pour VOSK)
- pip (gestionnaire de paquets Python)
- ffmpeg (pour le traitement audio et, optionnellement, la conversion WAV IVR 8 kHz)
- PortAudio (pour la capture micro : `sounddevice` sous Linux utilise `portaudio19-dev`)

## Installation

### 1. Installation des dépendances système

Sur Debian/Ubuntu/Raspberry Pi OS :

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-dev portaudio19-dev libasound2-dev ffmpeg
```

**Windows** : la capture micro utilise `sounddevice` (dans `requirements.txt`). Pour générer les WAV téléphoniques 8 kHz (script `test_patterns_voice.py`), installez ffmpeg dans votre environnement conda : `conda install -c conda-forge "ffmpeg=4.3.1"`.

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

**Raspberry Pi** : Whisper provoque souvent "Illegal instruction" sur ARM. Utiliser Vosk sur le Pi :

- Dans `config/config.yaml` : `voice_recognition_engine: vosk`, et `vosk_model_path` comme ci-dessus.
- Ou dans `.env` : `VOICE_RECOGNITION_ENGINE=vosk`.
- Installer le modèle français VOSK (voir commandes ci-dessus).

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

### Windows : "No module named 'pyaudio._portaudio'"

Le module C de PyAudio (PortAudio) n'est souvent pas fourni par un simple `pip install pyaudio`. Sous conda, le paquet conda-forge inclut PortAudio ; pas besoin d'installer portaudio à part.

- **Avec conda** : `conda install -c conda-forge pyaudio`. Si une ancienne version pip/distutils est déjà là et que `pip uninstall pyaudio` échoue ("distutils installed project") :
  1. Supprimer à la main le dossier `pyaudio` dans le site-packages de l'env :  
     `C:\Users\<user>\miniconda3\envs\vocalguard\Lib\site-packages\pyaudio`  
     (et éventuellement `PyAudio-*.dist-info` dans le même dossier)
  2. Puis : `conda install -c conda-forge pyaudio -y`
- Sinon, télécharger un fichier `.whl` depuis [pythonlibs (PyAudio)](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) pour votre version de Python, puis `pip install chemin/vers/PyAudio‑...‑.whl`

### Erreurs Whisper

1. Vérifier que `ffmpeg` est installé
2. Pour utiliser le GPU : installer `torch` avec support CUDA

### "Illegal instruction" sur Raspberry Pi

Whisper (PyTorch) n'est en général pas compatible avec l'ARM du Pi. Utiliser Vosk à la place : `VOICE_RECOGNITION_ENGINE=vosk` dans `.env` ou dans la config, puis installer un modèle VOSK (voir section VOSK ci-dessus).

### Windows : "Le module spécifié est introuvable" (torch_python.dll)

PyTorch peut échouer au chargement sous Windows (conda, runtime C++ manquant, etc.). Pour éviter Whisper/torch, utiliser Vosk : dans le fichier `.env` à la racine du projet, ajouter `VOICE_RECOGNITION_ENGINE=vosk`, installer le paquet `vosk` (`pip install vosk`), puis télécharger un modèle français depuis [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models) et définir `VOSK_MODEL_PATH` vers le dossier du modèle (ex. `C:\Users\...\vosk-model-fr-0.22`).

### Erreurs de base de données

1. Vérifier les permissions d'écriture dans le dossier de données
2. Vérifier que SQLite est installé : `sudo apt-get install sqlite3`

## Prochaines étapes

- Consulter la [documentation de l'API](API.md)
- Configurer les règles de blocage
- Personnaliser les messages vocaux

