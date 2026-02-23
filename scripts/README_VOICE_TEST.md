# Test de l'interface vocale en local

Les scripts de ce dossier permettent de tester l'interface vocale de VocalGuard sans modem, en utilisant le micro et les haut-parleurs du PC.

## Prérequis

- Python 3.9+ (3.11+ recommandé pour VOSK)
- Microphone fonctionnel
- Haut-parleurs ou casque audio
- Dépendances : `sounddevice` (capture micro), `pygame` ou équivalent (lecture audio), `pydub` + `ffmpeg` (optionnel, pour WAV téléphone 8 kHz)

## Installation des dépendances

```bash
pip install sounddevice pygame pydub
```

- **Windows** : la capture micro utilise `sounddevice` (plus fiable que PyAudio). Pour générer les WAV IVR 8 kHz à partir du TTS (gTTS produit du MP3), installez ffmpeg dans l'environnement conda : `conda install -c conda-forge "ffmpeg=4.3.1"`.
- **Linux** : `sudo apt-get install portaudio19-dev` puis `pip install sounddevice`.

## Scripts disponibles

### test_ollama_voice.py – Conversation avec Ollama

```bash
python scripts/test_ollama_voice.py
```

- Reconnaissance vocale (VOSK en temps réel avec détection de fin de phrase, ou Whisper en bloc)
- Réponse générée par Ollama (IA locale)
- Synthèse et lecture de la réponse

Avec `VOICE_RECOGNITION_ENGINE=vosk`, le micro est écouté en continu jusqu'à une pause (fin de phrase), puis la phrase est envoyée à Ollama.

### test_patterns_voice.py – Conversation par intents (sans Ollama)

```bash
python scripts/test_patterns_voice.py
```

- Reconnaissance VOSK en temps réel (fin de phrase)
- Réponse choisie selon des **intents** définis dans `config/intents_ivr.yaml`
- Génération de WAV 8 kHz (téléphone) dans `ivr_wav/` et lecture locale

Idéal pour tester un IVR type téléphone fixe sans dépendance à un modèle IA. Voir [config/README_INTENTS_IVR.md](../config/README_INTENTS_IVR.md).

### generate_intents_tts_examples.py – Exemples TTS à partir des intents (edge-tts)

```bash
python scripts/generate_intents_tts_examples.py
```

- Affiche les **voix disponibles** (toutes ou françaises uniquement) via edge-tts
- Menu : choisir une voix, puis générer un fichier audio par intent (réponse TTS)
- Fichiers générés dans `ivr_wav/` en WAV 8 kHz si pydub/ffmpeg sont installés, sinon en MP3
- Utile pour pré-générer les messages IVR avec une voix Microsoft (Denise, Henri, etc.) au lieu de gTTS/pyttsx3

Prérequis : `pip install edge-tts`. Optionnel : pydub + ffmpeg pour la conversion en WAV téléphone.

### test_voice_conversation.py

```bash
python scripts/test_voice_conversation.py
```

Boucle classique : enregistrement 5 secondes, transcription, réponse via patterns (fichier `config/responses.yaml`), synthèse et lecture.

### Via l'interface web

1. Démarrez l'application : `.\run.ps1` (Windows) ou `./run.sh` (Linux/Mac)
2. Ouvrez votre navigateur : `http://localhost:8000`
3. Cliquez sur l'onglet "Test vocal"
4. Utilisez les trois sections :
   - **Synthèse vocale** : Entrez un texte et générez l'audio
   - **Reconnaissance vocale** : Uploadez un fichier audio pour le transcrire
   - **Test de conversation** : Uploadez un fichier audio, le système génère une réponse et la synthétise

## Personnalisation des réponses

- **test_patterns_voice** : éditez `config/intents_ivr.yaml` (intents, keywords, response, filename WAV). Voir [config/README_INTENTS_IVR.md](../config/README_INTENTS_IVR.md).
- **test_voice_conversation** : modifiez `generate_response()` dans le script ou utilisez `config/responses.yaml` ; voir [config/README_RESPONSES.md](../config/README_RESPONSES.md).
- **API web** : `backend/api/routes/voice_test.py` et `config/responses.yaml`.

## Exemple de conversation

```
VocalGuard: Bonjour ! Je suis VocalGuard. Comment puis-je vous aider ?
Vous: Bonjour, je veux bloquer un numéro
VocalGuard: Je peux vous aider à bloquer des numéros indésirables.
Vous: Merci
VocalGuard: De rien, c'est un plaisir de vous aider !
Vous: Au revoir
VocalGuard: Au revoir ! À bientôt.
```

## Dépannage

### Erreur "sounddevice" ou micro inutilisable
Installez avec `pip install sounddevice`. Sous Windows (conda), vous pouvez aussi utiliser `conda install -c conda-forge python-sounddevice`. Sous Linux : `sudo apt-get install portaudio19-dev`.

### Erreur "No module named 'pygame'"
Installez pygame avec `pip install pygame` ou utilisez une autre méthode de lecture (winsound, playsound).

### Erreur lors de la conversion WAV IVR (ffmpeg / ffprobe)
Le script test_patterns_voice convertit le TTS (MP3) en WAV 8 kHz via pydub ; il faut ffmpeg. Sous Windows avec conda : `conda install -c conda-forge "ffmpeg=4.3.1"`. Si ffmpeg est absent, la génération des WAV IVR échoue mais le script peut continuer.

### Le micro ne fonctionne pas
Vérifiez que le microphone est connecté et autorisé dans les paramètres système.

### La transcription est vide
Parlez clairement après le message « Parlez. » ; avec VOSK en temps réel, faites une courte pause en fin de phrase pour déclencher la reconnaissance.

