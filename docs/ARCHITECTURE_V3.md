# Architecture VocalGuard v3 - Backend/Frontend unifiés

## Vue d'ensemble

Cette version formalise la nouvelle architecture de VocalGuard:

- **Backend Python** unifié dans le package `backend/` (modem, appels, OSINT, RDV, devis, mini-CRM, API REST, Celery).
- **Frontend web** moderne dans `frontend/` (Next.js + TypeScript) pour DanielCraftFr.
- **Base de données SQLite** en développement, facilement remplaçable par PostgreSQL en production.

L'objectif est d'avoir une structure claire, découpée par responsabilités, et prête à évoluer.

## Structure du dépôt

```text
VocalGuard/
  backend/                   # Backend Python (FastAPI, modem, OSINT, RDV, devis...)
    api/                     # API REST FastAPI (routes + modèles Pydantic)
    core/                    # Cœur téléphonie (modem, CallManager, events, config)
    voice/                   # Reconnaissance et synthèse vocale
    services/                # Logique métier (appels, blocage, OSINT, conversation, phone DB...)
    repositories/            # Repositories SQLAlchemy (calls, callers, voicemails, règles de blocage...)
    database/                # Modèles SQLAlchemy + initialisation (SQLite en dev)
    osint/                   # Service OSINT persistant (PhoneOsintService)
    workers/                 # Tâches Celery (OSINT, futurs emails/PDF...)
    ai/                      # Intégration IA locale (patterns + ML)
    web/                     # Ancienne interface statique (peut être conservée comme fallback)
    domain/                  # Espace pour les services métier plus hauts niveaux (RDV, devis, CRM)
    settings/                # Surcouche de configuration si besoin
    main.py                  # Point d'entrée FastAPI (backend.main:app)
    celery_app.py            # Configuration Celery (backend.celery_app.celery_app)
    requirements.txt         # Dépendances backend

  frontend/                  # Frontend web (Next.js + TypeScript)
    src/
      app/                   # Router Next.js (pages: dashboard, appels, RDV, devis, clients, etc.)
      components/            # Layout, sidebar, topbar, cartes, tables...
      services/              # Clients d'API (calls, osint, appointments, quotes, customers, settings)
      styles/                # Styles globaux

  docs/                      # Documentation
  config/                    # Fichiers de configuration (YAML des réponses, modem, etc.)
  logs/                      # Logs runtime (backend)
  vocalguard.db              # Base SQLite de développement
```

## Backend - Découpage par responsabilités

### 1. `backend/core/`

- `config.py` : configuration principale (API, modem, DB, OSINT, voicemail...).
- `modem_handler.py` : gestion du modem (ports série, commandes AT, détection RING / Caller ID).
- `events.py` : bus d'événements (architecture orientée événements pour CALL_INCOMING, CALL_COMPLETED, etc.).
- `call_manager.py` : orchestrateur d'appels:
  - écoute les événements du modem,
  - crée les entrées d'appel via `CallService`,
  - applique les règles de blocage (`BlockService`),
  - lance l'interaction vocale (STT/TTS + `ConversationService`),
  - publie les événements de fin d'appel.

### 2. `backend/voice/`

- `recognition.py` : intégration Whisper/Vosk (reconnaissance vocale).
- `synthesis.py` : intégration pyttsx3/gTTS (synthèse vocale).

### 3. `backend/database/`

- `models.py` : modèles SQLAlchemy:
  - `Caller`, `Call`, `Voicemail`, `BlockRule`
  - `FrenchPhonePrefix` (données opérateurs/préfixes FR)
  - `PhoneNumberProfile` (profil OSINT structuré)
  - `Customer` (dossier client central)
  - `Appointment` (RDV)
  - `Quote` (devis, totaux en centimes)
- `database.py` : initialisation en mode synchrone:
  - `init_database(database_url)` : crée l'engine, la factory de sessions et les tables.
  - `get_db()` : fournit une `Session` SQLAlchemy (utilisée par FastAPI via les dépendances).

En développement, la base est une SQLite locale `sqlite:///vocalguard.db` à la racine.

### 4. `backend/repositories/`

- `base.py` : repository de base (CRUD générique).
- `call_repository.py` : accès aux appels.
- `caller_repository.py` : accès aux appelants.
- `voicemail_repository.py` : messages vocaux.
- `block_rule_repository.py` : règles de blocage.

Les services métiers consomment ces repositories, jamais la DB brute.

### 5. `backend/services/`

Services métier principaux:

- `call_service.py` :
  - crée les appels entrants (`create_incoming_call`),
  - met à jour les statuts (`answer_call`, `complete_call`, `miss_call`, `block_call`),
  - déclenche automatiquement l'OSINT persistant via `PhoneOsintService`.
- `block_service.py` : logique de blocage (liste noire, règles, OSINT).
- `osint_service.py` : intégration détaillée des outils OSINT (phoneinfoga, NumLookup, OpenCNAM, etc.).
- `french_phone_detector.py` / `french_phone_db.py` : enrichissement des numéros FR (préfixes, zones, opérateurs).
- `conversation_service.py` :
  - encapsule la génération de réponses vocales (patterns + fallback),
  - utilisé par `CallManager` pour répondre aux transcriptions.
- `person_lookup.py`, `commercial_detector.py`, `french_phone_data.py` : briques complémentaires OSINT / détection commerciale.

### 6. `backend/osint/` + `backend/workers/`

- `osint/services.py` :
  - `PhoneOsintService`:
    - normalise les numéros,
    - crée/trouve un `PhoneNumberProfile`,
    - planifie un enrichissement asynchrone via Celery si besoin.
- `workers/osint_tasks.py` :
  - tâche Celery `run_osint_for_profile(profile_id)`:
    - charge le profil depuis la DB,
    - appelle `OSINTService.enrich_phone_number`,
    - recopie les champs pertinents dans `PhoneNumberProfile` (opérateur, région, réputation, flags spam…),
    - met à jour `last_checked_at` et `raw_data`.

### 7. `backend/api/`

- `api/app.py` :
  - crée l'app FastAPI,
  - configure CORS,
  - monte les routes `/api/v1/...`,
  - initialise la DB au démarrage (`on_startup` + `init_database`),
  - sert l'ancienne interface statique sous `/` si présente.
- `api/dependencies.py` :
  - fournit `get_db`, `get_call_service`, `get_block_service`, etc. pour FastAPI.
- `api/models.py` :
  - modèles Pydantic de réponse/demande:
    - `CallResponse`, `CallListResponse`
    - `Caller*`, `VoicemailResponse`
    - `PhoneNumberProfileResponse`, `OsintReputationResponse`
    - `Appointment*`, `Quote*`, `Customer*`, `SettingsResponse`
- `api/routes/` :
  - `calls.py` : `/api/v1/calls`
  - `callers.py` : `/api/v1/callers`
  - `voicemails.py` : `/api/v1/voicemails`
  - `osint.py` : `/api/v1/osint/...`
  - `appointments.py` : `/api/v1/appointments`
  - `quotes.py` : `/api/v1/quotes`
  - `customers.py` : `/api/v1/customers`
  - `settings.py` : `/api/v1/settings`
  - `config.py`, `voice_test.py` : endpoints de config/tests.

## Frontend - Next.js

Le frontend consomme les endpoints `backend` via des services typés.

Exemples:

- `src/services/callsApi.ts` :
  - `fetchCallsWithOsint()` appelle `/api/v1/calls` puis `/api/v1/osint/reputation/{phone_number}`.
- `src/services/appointmentsApi.ts` :
  - `fetchAppointments()` → `/api/v1/appointments`.
- `src/services/quotesApi.ts`, `customersApi.ts` : devis et clients.

Les pages principales:

- `/dashboard` : synthèse (appels, RDV, devis, OSINT).
- `/calls` : table des appels + réputation OSINT.
- `/appointments`, `/quotes`, `/customers` : vues CRM/rendez-vous/devis.
- `/settings`, `/kb`, `/simulator` : configuration métier, base de connaissances, simulateur d'appel.

## Flux d'un appel avec OSINT et CRM

1. Le modem détecte un appel (`RING` / `Caller ID`) via `ModemHandler`.
2. `CallManager` crée un `Call` via `CallService.create_incoming_call`.
3. `CallService`:
   - associe un `Caller`,
   - passe le numéro à `PhoneOsintService.ensure_profile_for_number`:
     - crée/met à jour un `PhoneNumberProfile`,
     - planifie une tâche Celery si le profil est trop ancien.
4. Selon le blocage (`BlockService`), l'appel est:
   - rejeté (message court + raccrochage),
   - ou pris en charge (interaction vocale + éventuellement RDV/devis plus tard).
5. En tâche de fond, Celery enrichit `PhoneNumberProfile`.
6. Le frontend affiche la réputation dans:
   - la liste des appels (`/calls`),
   - la fiche client (`/customers`).

## Remarques sur l'évolution

- En dev, SQLite (`vocalguard.db`) suffit pour tester tout le flux.
- En prod, il suffira de passer `database_url` sur PostgreSQL (et d'ajouter un moteur async si besoin).
- La séparation `api / core / services / repositories / database` facilite:
  - tests unitaires et d'intégration,
  - introduction future de workflows plus riches (prise de RDV automatique, génération de devis depuis la conversation),
  - ajout d'autres workers Celery (envoi de mails, génération PDF, relances automatiques).

