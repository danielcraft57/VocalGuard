# Déploiement VocalGuard sur Raspberry Pi

## Résumé

Exemple de déploiement sur un Raspberry Pi (ex. votre-serveur.lan) :
- ✅ Moteur vocal patterns/ML configuré
- ✅ Environnement virtuel Python créé
- ✅ Toutes les dépendances installées
- ✅ Configuration audio USB configurée
- ✅ Scripts de test vocaux fonctionnels

## Configuration Audio

### Problème résolu

Le fichier `~/.asoundrc` était corrompu, causant des erreurs PyAudio. Solution :

```bash
# Sur le Raspberry Pi
cd ~/VocalGuard
source venv/bin/activate
python scripts/fix_asoundrc.py
```

### Périphérique USB

- **Carte audio** : Carte 0 (USB PnP Sound Device)
- **Taux d'échantillonnage** : 48000 Hz (détecté automatiquement)
- **Entrées** : 1 (micro)
- **Sorties** : 2 (stéréo)

### Configuration ALSA

Le fichier `~/.asoundrc` configure ALSA pour utiliser le périphérique USB par défaut :

```alsa
pcm.!default {
    type plug
    slave {
        pcm "hw:0,0"
    }
}
ctl.!default {
    type hw
    card 0
}
```

## Utilisation

### Test de conversation vocale

```bash
ssh pi@votre-serveur
cd ~/VocalGuard
source venv/bin/activate
python scripts/test_patterns_voice.py
```

Le script va :
1. Charger VOSK/Whisper pour la transcription
2. Initialiser pyttsx3 pour la synthèse vocale
3. Attendre que tu parles dans le micro USB
4. Transcrire, matcher des intents/patterns, et répondre vocalement

### Commandes de test

```bash
# Test PyAudio
python scripts/test_pyaudio.py

# Test d'enregistrement
python scripts/test_record.py

# Test de lecture audio
aplay /usr/share/sounds/alsa/Front_Left.wav
```

## Dépannage

### Erreur PyAudio "Unanticipated host error"

Le fichier `~/.asoundrc` est corrompu. Réparer avec :
```bash
python scripts/fix_asoundrc.py
```

### Pas de son

1. Vérifier que le périphérique USB est branché : `aplay -l`
2. Vérifier la configuration : `cat ~/.asoundrc`
3. Tester manuellement : `aplay /usr/share/sounds/alsa/Front_Left.wav`

### Erreur "Invalid sample rate"

Le script détecte automatiquement le taux d'échantillonnage supporté (généralement 48000 Hz pour les périphériques USB).

### Warnings ALSA

Les warnings ALSA concernant des périphériques virtuels inexistants sont normaux et peuvent être ignorés. Ils n'empêchent pas le fonctionnement.

## Structure du projet

```
~/VocalGuard/
├── venv/              # Environnement virtuel Python
├── vocalguard/        # Code source VocalGuard
├── scripts/           # Scripts de test et utilitaires
│   ├── test_patterns_voice.py
│   ├── test_pyaudio.py
│   ├── test_record.py
│   └── fix_asoundrc.py
├── docs/              # Documentation
├── config/            # Configuration
└── .env              # Variables d'environnement
```

## Configuration conversation

- **Moteur** : patterns + intents
- **Fichier** : `config/intents_ivr.yaml`
- **Synthèse** : pyttsx3/gTTS

## Prochaines étapes

1. ✅ Système fonctionnel avec micro-casque USB
2. ✅ Conversation vocale opérationnelle
3. 🔄 Intégration avec CallManager pour les appels téléphoniques
4. 🔄 Optimisation des performances audio
