# Configuration Audio pour Raspberry Pi

## Problème

Sur un Raspberry Pi sans interface graphique ou en SSH, l'audio peut ne pas fonctionner par défaut car :
- PulseAudio n'est pas démarré
- ALSA n'a pas de périphérique par défaut configuré
- Le périphérique USB n'est pas sélectionné

## Solution

### 1. Vérifier les périphériques audio

```bash
# Périphériques de lecture
aplay -l

# Périphériques d'enregistrement
arecord -l

# Périphériques USB
lsusb | grep -i audio
```

### 2. Configurer ALSA pour utiliser le périphérique USB

Créer le fichier `~/.asoundrc` :

```bash
cat > ~/.asoundrc << 'EOF'
# Configuration ALSA pour périphérique USB par défaut
pcm.!default {
    type plug
    slave {
        pcm "hw:0,0"  # Ajuster selon 'aplay -l' (card 0 = USB)
    }
}
ctl.!default {
    type hw
    card 0
}
EOF
```

**Important** : Ajustez `card 0` selon la sortie de `aplay -l`. Si votre périphérique USB est la carte 1, utilisez `hw:1,0` et `card 1`.

### 3. Tester l'audio

```bash
# Test de lecture
aplay /usr/share/sounds/alsa/Front_Left.wav

# Test d'enregistrement (5 secondes)
arecord -d 5 test.wav && aplay test.wav
```

### 4. Démarrer PulseAudio (optionnel)

Si vous préférez utiliser PulseAudio :

```bash
# Démarrer PulseAudio
pulseaudio --start --exit-idle-time=-1

# Vérifier qu'il fonctionne
pulseaudio --check -v
```

### 5. Utiliser avec VocalGuard

Le script `test_ollama_voice.py` essaie automatiquement :
1. `aplay` avec le périphérique par défaut (`-D default`)
2. `paplay` (PulseAudio) en fallback

Si aucun ne fonctionne, vérifiez :
- Que le fichier `~/.asoundrc` existe et est correct
- Que le périphérique USB est bien branché
- Que les permissions audio sont correctes (ajouter l'utilisateur au groupe `audio`)

```bash
# Ajouter l'utilisateur au groupe audio
sudo usermod -a -G audio $USER
# Redémarrer la session SSH
```

## Dépannage

### Erreur "cannot find card"
- Vérifiez `aplay -l` pour voir les cartes disponibles
- Ajustez le numéro de carte dans `~/.asoundrc`

### Erreur "device busy"
- Arrêtez les autres applications audio
- Redémarrez ALSA : `sudo alsa force-reload`

### Pas de son mais pas d'erreur
- Vérifiez le volume : `alsamixer`
- Testez avec un autre fichier WAV
- Vérifiez que le casque/haut-parleurs sont bien branchés

### PulseAudio ne démarre pas
- Vérifiez les logs : `pulseaudio -v`
- Essayez de démarrer manuellement : `pulseaudio --start`
- Si ça ne fonctionne pas, utilisez ALSA directement avec `aplay`
