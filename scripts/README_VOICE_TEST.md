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

### test_patterns_voice.py – Conversation par intents

```bash
python scripts/test_patterns_voice.py
```

- Reconnaissance VOSK en temps réel (fin de phrase)
- Réponse choisie selon des **intents** définis dans `config/intents_ivr.yaml`
- Génération de WAV 8 kHz (téléphone) dans `ivr_wav/` et lecture locale

Idéal pour tester un IVR type téléphone fixe basé sur des patterns et intents. Voir [config/README_INTENTS_IVR.md](../config/README_INTENTS_IVR.md).

### generate_intents_tts_examples.py – Exemples TTS à partir des intents (edge-tts)

```bash
python scripts/generate_intents_tts_examples.py
```

- Affiche les **voix disponibles** (toutes ou françaises uniquement) via edge-tts
- Menu : choisir une voix, puis générer un fichier audio par intent (réponse TTS)
- Fichiers générés dans `ivr_wav/` en WAV 8 kHz si pydub/ffmpeg sont installés, sinon en MP3
- Utile pour pré-générer les messages IVR avec une voix Microsoft (Denise, Henri, etc.) au lieu de gTTS/pyttsx3

Prérequis : `pip install edge-tts`. Optionnel : pydub + ffmpeg pour la conversion en WAV téléphone.

### test_modem_answer_play_record.py – Test modem (décrocher, WAV, enregistrer)

À lancer sur le Raspberry Pi avec modem et carte audio (ex. pi@raspberrypi.local). Décroche un appel entrant, joue un fichier WAV (ex. `ivr_wav/ivr_message.wav`), enregistre un message répondeur dans `recordings/voicemail_*.wav`, puis raccroche. Voir [scripts/transfer_and_test_modem_node14.md](transfer_and_test_modem_node14.md) pour le transfert vers le Pi et le lancement avec le venv.

```bash
# Sur le Pi, après transfert
cd ~/VocalGuard && source venv/bin/activate
python scripts/test_modem_answer_play_record.py
```

- **Prérequis sur le Pi** : `alsa-utils` (aplay, arecord), modem détecté (port série).
- **Test pratique** : lancer un appel de test depuis un autre téléphone et vérifier :
  - que le modem décroche,
  - que le message joué (WAV) est bien entendu côté appelant,
  - que le message répondeur est bien enregistré dans `recordings/`.

#### Lancer le test modem en mode démon (service systemd)

Pour avoir le test modem qui tourne en tâche de fond avec un fichier de log dédié :

1. Copier le service sur le Pi :

   ```bash
   scp vocalguard-test-modem.service pi@raspberrypi.local:/tmp/
   ssh pi@raspberrypi.local "sudo mv /tmp/vocalguard-test-modem.service /etc/systemd/system/"
   ssh pi@raspberrypi.local "sudo systemctl daemon-reload && sudo systemctl enable vocalguard-test-modem.service"
   ssh pi@raspberrypi.local "sudo systemctl start vocalguard-test-modem.service"
   ```

2. Le service exécute en boucle :

   ```bash
   cd /home/pi/VocalGuard
   source venv/bin/activate
   python scripts/test_modem_answer_play_record.py
   ```

3. Les logs sont disponibles :

   - dans le journal systemd : `journalctl -u vocalguard-test-modem.service -f`
   - dans le fichier : `/home/pi/VocalGuard/logs/test_modem_answer_play_record.log`

Pour arrêter/redémarrer le démon :

```bash
sudo systemctl stop vocalguard-test-modem.service
sudo systemctl restart vocalguard-test-modem.service
```

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

