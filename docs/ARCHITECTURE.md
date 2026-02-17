# Architecture VocalGuard

## Vue d'ensemble

VocalGuard est un système moderne de gestion d'appels avec interface vocale intelligente. Il est conçu avec une architecture modulaire et extensible.

## Structure du projet

```
VocalGuard/
├── vocalguard/              # Package principal
│   ├── __init__.py
│   ├── main.py              # Point d'entrée
│   ├── core/                # Cœur du système
│   │   ├── config.py        # Configuration
│   │   ├── modem_handler.py # Gestion du modem
│   │   └── call_manager.py  # Gestion des appels
│   ├── voice/               # Module vocal
│   │   ├── recognition.py   # Reconnaissance vocale
│   │   ├── synthesis.py     # Synthèse vocale
│   │   └── processor.py     # Traitement audio (à venir)
│   ├── api/                 # API REST
│   │   ├── app.py           # Application FastAPI
│   │   ├── routes/          # Routes API
│   │   └── models.py        # Modèles Pydantic
│   ├── database/            # Base de données
│   │   ├── models.py        # Modèles SQLAlchemy
│   │   └── database.py      # Connexion DB
│   └── web/                 # Interface web (à venir)
├── config/                  # Configuration
├── tests/                   # Tests
├── docs/                    # Documentation
└── requirements.txt         # Dépendances
```

## Composants principaux

### 1. Core (Cœur du système)

#### Config
Gère la configuration de l'application depuis des fichiers YAML ou des variables d'environnement.

#### ModemHandler
Gère la communication avec le modem USB :
- Détection automatique du port
- Envoi de commandes AT
- Surveillance des appels entrants
- Décrochage/raccrochage

#### CallManager
Orchestre le traitement des appels :
- Détection des appels entrants
- Vérification du blocage
- Gestion de l'interaction vocale
- Enregistrement des messages vocaux

### 2. Voice (Module vocal)

#### VoiceRecognition
Reconnaissance vocale avec support de :
- **Whisper** : Modèle OpenAI pour la transcription précise
- **VOSK** : Modèle léger pour la reconnaissance en temps réel

#### VoiceSynthesis
Synthèse vocale avec support de :
- **pyttsx3** : Synthèse vocale locale
- **gTTS** : Google Text-to-Speech (nécessite internet)

### 3. API (API REST)

API REST moderne avec FastAPI :
- `/api/v1/calls` - Gestion des appels
- `/api/v1/callers` - Gestion des appelants
- `/api/v1/voicemails` - Messages vocaux
- `/api/v1/config` - Configuration

### 4. Database (Base de données)

Modèles SQLAlchemy pour :
- **Caller** : Appelants (numéros, statuts, notes)
- **Call** : Historique des appels
- **Voicemail** : Messages vocaux enregistrés
- **BlockRule** : Règles de blocage

## Flux de traitement d'un appel

1. **Détection** : Le ModemHandler détecte un appel entrant (RING)
2. **Caller ID** : Récupération du numéro et du nom de l'appelant
3. **Vérification** : Le CallManager vérifie si l'appelant est bloqué
4. **Traitement** :
   - Si bloqué : Message de blocage et raccrochage
   - Si autorisé : Décrochage et interaction vocale
5. **Interaction** :
   - Message d'accueil vocal
   - Enregistrement de la réponse
   - Transcription avec VoiceRecognition
   - Traitement de la commande vocale
   - Réponse vocale avec VoiceSynthesis
6. **Enregistrement** : Sauvegarde dans la base de données

## Technologies utilisées

- **FastAPI** : Framework web moderne et performant
- **SQLAlchemy** : ORM pour la base de données
- **Whisper/VOSK** : Reconnaissance vocale
- **pyttsx3/gTTS** : Synthèse vocale
- **pyserial** : Communication avec le modem
- **Loguru** : Logging moderne

## Extensibilité

Le système est conçu pour être extensible :

- **Nouveaux moteurs vocaux** : Ajouter des classes dans `voice/`
- **Nouveaux services de blocage** : Étendre `CallManager._check_if_blocked()`
- **Nouvelles routes API** : Ajouter dans `api/routes/`
- **Nouveaux modèles** : Ajouter dans `database/models.py`

## Performance

- Traitement asynchrone avec `asyncio`
- Base de données avec connexions poolées
- Cache des fichiers audio générés
- Support GPU pour Whisper (optionnel)

