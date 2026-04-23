# Transfert vers Raspberry Pi et test modem

Procedure pour transferer VocalGuard sur **pi@raspberrypi.local** et lancer le test modem (decrocher, jouer un WAV, enregistrer un message).

## Pre-requis

- Acces SSH a `pi@raspberrypi.local`
- Modem USB branche sur le Raspberry Pi (port serie pour ATA/ATH)
- Carte audio ou modem avec interface audio connectee a la ligne (ALSA)
- Fichier WAV a jouer : generer avec `generate_intents_tts_examples.py` (ex. `ivr_wav/ivr_message.wav`) ou utiliser un WAV 8 kHz mono

## 1. Transferer le projet sur Raspberry Pi

Depuis ta machine (dans le dossier VocalGuard) :

```bash
# Avec variable d'environnement (bash/WSL/Git Bash)
export RPI_HOST=pi@raspberrypi.local
./scripts/deploy_to_rpi.sh
```

Sous PowerShell :

```powershell
$env:RPI_HOST = "pi@raspberrypi.local"
.\scripts\deploy_to_rpi.ps1
```

Si tu n'as pas de script PowerShell, utilise rsync a la main :

```bash
rsync -avz --exclude 'venv' --exclude '__pycache__' --exclude '.git' --exclude '*.db' --exclude 'audio_cache' --exclude 'logs' -e ssh . pi@raspberrypi.local:~/VocalGuard/
```

Puis sur le Pi, installer les dependances si besoin :

```bash
ssh pi@raspberrypi.local "cd ~/VocalGuard && source venv/bin/activate && pip install -r requirements.txt"
```

## 2. Preparer le WAV et la config sur le Pi

Les WAV generes par `generate_intents_tts_examples.py` et par le flux IVR (test_patterns_voice) sont en **8 kHz, mono, 8-bit** : compatibles modem Conexant (mode voix serie). Pas besoin de conversion.

- Le script cherche par defaut `ivr_wav/ivr_message.wav`. Si le dossier `ivr_wav` est vide, genere les WAV en local puis transfere le dossier, ou copie un WAV de test vers `ivr_wav/ivr_message.wav`.
- Optionnel : creer `config/config.yaml` sur le Pi avec `modem_port` si le modem n'est pas auto-detecte (ex. `modem_port: "/dev/ttyACM0"`).

## 3. Lancer le test modem sur Raspberry Pi (mode interactif)

SSH sur le Pi puis :

```bash
ssh pi@raspberrypi.local
cd ~/VocalGuard
source venv/bin/activate
python scripts/test_modem_answer_play_record.py
```

Le script va :
1. Initialiser le modem (detection du port si non configure)
2. Attendre un appel entrant (RING)
3. Decrocher (ATA)
4. Jouer le fichier WAV vers la ligne (mode voix serie VTX ou aplay)
5. Enregistrer jusqu'a 30 s depuis la ligne (mode voix serie VRX ou arecord) dans `recordings/voicemail_YYYYMMDD_HHMMSS.wav`
6. Raccrocher (ATH)

Arret : Ctrl+C.

## 3bis. Lancer le test modem en mode démon (service systemd)

Pour ne pas avoir à laisser une session SSH ouverte et garder le test en écoute en permanence, tu peux utiliser le service systemd `vocalguard-test-modem.service` (à copier sur le Pi).

1. Copier le service sur le Pi :

   ```bash
   scp vocalguard-test-modem.service pi@raspberrypi.local:/tmp/
   ssh pi@raspberrypi.local "sudo mv /tmp/vocalguard-test-modem.service /etc/systemd/system/"
   ssh pi@raspberrypi.local "mkdir -p /home/pi/VocalGuard/logs"
   ssh pi@raspberrypi.local "sudo systemctl daemon-reload"
   ssh pi@raspberrypi.local "sudo systemctl enable vocalguard-test-modem.service"
   ssh pi@raspberrypi.local "sudo systemctl start vocalguard-test-modem.service"
   ```

2. Le service tourne alors en tâche de fond, surveille les appels entrants et écrit les logs dans :

   - `journalctl -u vocalguard-test-modem.service`
   - `/home/pi/VocalGuard/logs/test_modem_answer_play_record.log`

3. Commandes utiles :

   ```bash
   sudo systemctl status vocalguard-test-modem.service
   sudo systemctl stop vocalguard-test-modem.service
   sudo systemctl restart vocalguard-test-modem.service
   journalctl -u vocalguard-test-modem.service -f
   ```

Tu peux ensuite lancer un appel de test depuis un autre téléphone pour vérifier que :

- le modem décroche correctement,
- le message WAV est bien entendu côté appelant,
- le message répondeur est bien enregistré dans `recordings/voicemail_*.wav`.

## 4. Comment le WAV est joue vers la ligne (deux methodes)

**Methode 1 – Mode voix port serie (recommandé si modem Conexant)**  
Comme [callattendant](https://github.com/emxsys/callattendant) : le modem est mis en mode voix (AT+FCLASS=8, AT+VTX), puis les trames PCM 8 kHz sont envoyees sur le **même port serie**. L’appelant entend directement ce flux. Aucun peripherique ALSA n’est necessaire.  
Si le modem est detecte comme Conexant (ATI), le script utilise cette methode automatiquement. Sinon forcer avec : `export USE_MODEM_VOICE_MODE=1`

**Methode 2 – ALSA (aplay)**  
Si le modem expose une carte son ALSA reliee a la ligne, on peut jouer avec `aplay -D <device>`. Dans ce cas, identifier le device avec `aplay -l` et definir `ALSA_MODEM_DEVICE=hw:X,0`.

## 5. Peripherique ALSA (uniquement si methode ALSA)

Le WAV est joue **sur le modem** (vers la ligne telephonique). Il faut donc utiliser le peripherique ALSA associe au modem, pas celui du HDMI ou d'un haut-parleur USB.

Sur le Pi, lister les cartes :

```bash
aplay -l
arecord -l
```

Repérer la carte du modem (souvent "Conexant", "USB Audio" ou numero 1). Puis avant de lancer le script :

```bash
export ALSA_MODEM_DEVICE=hw:1,0
python scripts/test_modem_answer_play_record.py
```

Si lecture et enregistrement utilisent des devices differents (rare) :

```bash
export ALSA_MODEM_DEVICE=hw:1,0
export ALSA_MODEM_RECORD_DEVICE=hw:1,0
```

## 6. Depannage

- **Modem non detecte** : verifier `ls /dev/ttyACM* /dev/ttyUSB*` et mettre `modem_port` dans `config/config.yaml`.
- **aplay/arecord introuvables** : `sudo apt-get install alsa-utils`.
- **Permission denied sur le port serie** : `sudo usermod -aG dialout pi` puis se deconnecter/reconnecter.
- **Pas de son sur la ligne** : verifier que le peripherique ALSA utilise est bien celui relie a la ligne telephonique (voir `~/.asoundrc` et `fix_asoundrc.py` si besoin).
- **arecord : "No such file or directory"** : le device ALSA par defaut (souvent `default`) n'existe pas ou ne permet pas l'enregistrement. Lister les devices avec `arecord -L`, choisir un device valide (ex. `plughw:CARD=Modem,DEV=0`) et definir `ALSA_MODEM_RECORD_DEVICE` avant de lancer le script. Le test continue sans enregistrement si arecord echoue.
