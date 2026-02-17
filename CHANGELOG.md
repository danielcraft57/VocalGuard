# Changelog VocalGuard

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

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

