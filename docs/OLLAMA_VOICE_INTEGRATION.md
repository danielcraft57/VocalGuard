# Intégration Ollama avec Interaction Vocale

## Vue d'ensemble

VocalGuard peut maintenant utiliser Ollama pour des conversations vocales naturelles, comme avec un être humain. Le système combine :
- **Reconnaissance vocale** (Whisper/VOSK) : Voix → Texte
- **Ollama** : Texte → Réponse intelligente (avec historique)
- **Synthèse vocale** (pyttsx3/gTTS) : Texte → Voix

## Architecture

```
Microphone → Reconnaissance vocale → Ollama → Synthèse vocale → Haut-parleurs
                (Whisper/VOSK)      (IA locale)    (pyttsx3/gTTS)
```

## Configuration

### Variables d'environnement

Dans `.env` :
```env
# Ollama
OLLAMA_BASE_URL=http://node15.lan:11434
OLLAMA_MODEL=gemma-2b-chat
OLLAMA_TIMEOUT=30

# Voice
VOICE_RECOGNITION_ENGINE=whisper
VOICE_SYNTHESIS_ENGINE=pyttsx3
VOICE_LANGUAGE=fr
```

## Utilisation

### Test en local (micro + haut-parleurs)

```bash
# Test simple avec Ollama
python scripts/test_ollama_voice.py

# Test avec fallback vers patterns si Ollama indisponible
python scripts/test_voice_conversation.py
```

### Dans les appels téléphoniques

Ollama est automatiquement intégré dans le `CallManager`. Lors d'un appel :
1. L'appelant parle
2. Whisper transcrit la voix
3. Ollama génère une réponse intelligente (avec historique)
4. La réponse est synthétisée et jouée via le modem

## Fonctionnalités

### Historique de conversation

- Le modèle garde en mémoire les échanges précédents
- Peut se souvenir du nom de l'utilisateur
- Limite adaptée selon le modèle (6-20 échanges)

### Commandes spéciales

- "au revoir" / "quitter" → Termine la conversation
- "laisser un message" → Active l'enregistrement de message

### Fallback automatique

Si Ollama n'est pas disponible, le système utilise les patterns de réponse prédéfinis.

## Exemple de conversation

```
🤖 Bonjour ! Je suis VocalGuard avec Ollama. Comment puis-je vous aider ?
👤 Je m'appelle Loic
🤖 Bonjour Loic ! Comment allez-vous aujourd'hui ?
👤 Quel est mon nom ?
🤖 Ton nom est Loic.
👤 Au revoir
🤖 Au revoir ! À bientôt.
```

## Dépannage

### Ollama non disponible

```bash
# Vérifier la connexion
curl http://node15.lan:11434/api/tags

# Vérifier les logs
ssh pi@node15.lan "sudo journalctl -u ollama -f"
```

### Problèmes audio

- Vérifier que `pyaudio` est installé : `pip install pyaudio`
- Vérifier les permissions du microphone
- Tester avec `python scripts/test_voice_conversation.py`

### Réponses lentes / Timeout

- **Vérifier le préchargement** :
  ```bash
  ssh pi@node15.lan "sudo systemctl status ollama-preload"
  ssh pi@node15.lan "sudo systemctl restart ollama-preload"
  ```
- **Augmenter le timeout** dans `.env` : `OLLAMA_TIMEOUT=60` (ou plus)
- Utiliser `gemma-2b-fast` au lieu de `gemma-2b-chat` (plus rapide mais historique limité)
- Vérifier que le modèle est chargé :
  ```bash
  ssh pi@node15.lan "curl http://localhost:11434/api/generate -d '{\"model\":\"gemma-2b-chat\",\"prompt\":\"test\"}'"
  ```

## Performance

- **Temps de réponse total** : 5-20 secondes
  - Transcription : 2-5 secondes
  - Génération Ollama : 3-12 secondes (première requête peut être plus lente si modèle non préchargé)
  - Synthèse vocale : 1-2 secondes

### Optimisation

Pour des réponses plus rapides :
1. Vérifier que le service `ollama-preload` fonctionne :
   ```bash
   ssh pi@node15.lan "sudo systemctl status ollama-preload"
   ```
2. Augmenter le timeout si nécessaire dans `.env` :
   ```env
   OLLAMA_TIMEOUT=60  # ou plus si nécessaire
   ```
3. Utiliser `gemma-2b-fast` pour des réponses plus rapides (mais historique limité)

## Améliorations futures

- [ ] Détection de fin de parole (VAD - Voice Activity Detection)
- [ ] Streaming de la réponse (parler pendant la génération)
- [ ] Support de plusieurs langues
- [ ] Personnalisation de la voix de synthèse
