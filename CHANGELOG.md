# Changelog VocalGuard

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

## [Unreleased]

### Ajouté

- **Capture micro** : remplacement de PyAudio par **sounddevice** pour une installation plus fiable (notamment sous Windows).
- **Reconnaissance VOSK en temps réel** : nouvelle méthode `stream_vosk()` dans `backend/voice/recognition.py` ; détection de fin de phrase (pause) via `AcceptWaveform()` / `PartialResult()` / `FinalResult()`.
- **Script test_patterns_voice.py** : boucle vocale basée sur des intents, génération de WAV 8 kHz pour téléphone, lecture micro en flux.
- **Fichier d'intents IVR** : `config/intents_ivr.yaml` pour définir les stratégies question-réponse (keywords, response, filename WAV) ; chargeur dans `backend/voice/intents_loader.py`.
- **Documentation** : `config/README_INTENTS_IVR.md` (structure des intents, mention des packages NLU/ML Rasa/Snips et quand le ML est utile).

### Modifié

- **backend/voice/recognition.py** : `_transcribe_vosk` réinitialise le recognizer avec `Reset()` à chaque transcription ; compatibilité avec les versions de VOSK sans `SetSampleRate`.
- **scripts/voice_test_utils.py** : utilitaires communs pour les tests vocaux (logging, vérifs audio, lecture locale).
- **scripts/test_patterns_voice.py** : charge les intents depuis `config/intents_ivr.yaml`, utilise `find_intent()` et génère les WAV IVR (pydub + ffmpeg si disponible).
- **requirements.txt** : `sounddevice` et `pydub` ; note d'installation ffmpeg (conda-forge) pour la conversion WAV téléphone.
- **Documentation** : README, scripts/README_VOICE_TEST.md, docs/INSTALLATION.md mis à jour (sounddevice, ffmpeg Windows, scripts vocaux, intents IVR).

## [1.1.0] - 2026-01-26

### Amélioré

- **Architecture refactorisée** avec patterns modernes :
  - Pattern Repository pour l'accès aux données
  - Couche Service pour la logique métier
  - Système d'événements (EventBus) pour la communication découplée
  - Dependency Injection via FastAPI
- **Séparation des responsabilités** améliorée
- **Testabilité** améliorée avec injection de dépendances
- **Extensibilité** accrue avec le système d'événements
- **Code plus maintenable** avec une meilleure organisation

### Ajouté

- `vocalguard/repositories/` : Repositories pour l'accès aux données
  - `BaseRepository` : Repository de base avec méthodes CRUD communes
  - `CallRepository` : Gestion des appels
  - `CallerRepository` : Gestion des appelants
  - `VoicemailRepository` : Gestion des messages vocaux
  - `BlockRuleRepository` : Gestion des règles de blocage
- `vocalguard/services/` : Services métier
  - `CallService` : Service de gestion des appels
  - `BlockService` : Service de blocage avec règles configurables
- `vocalguard/core/events.py` : Système d'événements complet
- `vocalguard/api/dependencies.py` : Injection de dépendances FastAPI
- Documentation de l'architecture améliorée (`docs/ARCHITECTURE_V2.md`)

### Modifié

- `CallManager` : Refactorisé pour utiliser les services et le système d'événements
- Routes API : Utilisent maintenant les repositories et services via dependency injection
- Gestion des erreurs améliorée avec try/except appropriés

## [1.0.0] - 2026-01-26

### Ajouté

- Architecture modulaire complète
- Module de reconnaissance vocale (Whisper et VOSK)
- Module de synthèse vocale (pyttsx3 et gTTS)
- API REST complète avec FastAPI
- Gestionnaire de modem moderne
- Système de gestion d'appels avec interaction vocale
- Base de données avec SQLAlchemy
- Configuration flexible (YAML et variables d'environnement)
- Logging moderne avec Loguru
- Support Docker et docker-compose
- Documentation complète

### Basé sur

- Projet callattendant original (https://github.com/emxsys/callattendant)

