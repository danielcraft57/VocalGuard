# VocalGuard

Système moderne de gestion d'appels avec interface vocale intelligente, basé sur callattendant.

## Fonctionnalités

- Interface vocale moderne avec reconnaissance et synthèse vocale
- Blocage intelligent des appels indésirables avec OSINT
- Enrichissement OSINT des numéros (réputation, lieu, opérateur) via `phone_number_profiles`
- Services de réputation externes (NOMOROBO pour USA, SHOULDIANSWER pour hors USA)
- Page Appels avec recherche intelligente et filtres avancés (statut, réputation)
- Messagerie vocale avancée
- Interface web moderne et réactive (Next.js + TypeScript)
- API REST complète
- Support des modems USB modernes
- Intégration avec services de reconnaissance vocale (Whisper, VOSK)
- Base de données moderne avec SQLAlchemy
- Architecture modulaire et extensible avec patterns modernes (Repository, Service Layer, Event-Driven)

## Technologies

- Python 3.9+ (3.13 recommandé)
- FastAPI pour l'API REST
- SQLAlchemy pour la base de données
- Whisper/VOSK pour la reconnaissance vocale
- pyttsx3/gTTS pour la synthèse vocale
- Next.js + React (TypeScript) pour l'interface web
- Docker pour le déploiement

## Installation

### Prérequis

- Python 3.9 ou supérieur (3.13 recommandé)
- Modem USB compatible (US Robotics 5637, Zoom 3095, ou autres modems Conexant)
- Raspberry Pi 3B+ ou mieux (ou système Linux compatible)

### Installation rapide

#### Linux/Mac

```bash
chmod +x run.sh
./run.sh
```

#### Windows

```powershell
.\run.ps1
```

### Installation manuelle

```bash
# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt

# Créer les dossiers nécessaires
mkdir -p logs audio_cache data

# Configuration
cp config/config.example.yaml config/config.yaml
# Éditer config/config.yaml selon vos besoins
```

### Lancement

En développement (backend uniquement) :

```bash
cd VocalGuard
uvicorn backend.main:app --reload
```

- L'API sera accessible sur `http://localhost:8000`
- La documentation de l'API sera disponible sur `http://localhost:8000/docs`

Le backend utilise par défaut une base SQLite locale `vocalguard.db` à la racine.  
En production, vous pouvez passer sur PostgreSQL en ajustant `database_url` dans la configuration.

## Structure du projet

```text
VocalGuard/
  backend/                   # Backend Python (FastAPI, modem, OSINT, RDV, devis...)
    api/                     # API REST (routes + modèles Pydantic)
    core/                    # Cœur téléphonie (modem, CallManager, events, config)
    voice/                   # Reconnaissance et synthèse vocale
    services/                # Logique métier (appels, blocage, OSINT, conversation...)
    repositories/            # Repositories SQLAlchemy
    database/                # Modèles + initialisation DB
    osint/                   # Service OSINT persistant (PhoneNumberProfile)
    workers/                 # Tâches Celery (OSINT, futurs jobs)
    ai/                      # Intégration Ollama/IA
    web/                     # Ancienne interface statique (optionnelle)
    domain/                  # Espace pour les services métier plus hauts niveaux
    settings/                # Surcouche de configuration si besoin
    main.py                  # Point d'entrée FastAPI (backend.main:app)
    celery_app.py            # Configuration Celery
    requirements.txt         # Dépendances backend

  frontend/                  # Interface web (Next.js + TypeScript)
    src/
      app/                   # Pages: dashboard, appels, RDV, devis, clients, etc.
      components/            # Layout, sidebar, topbar, tables, cartes...
      services/              # Clients d'API typés (calls, osint, crm, settings)
      styles/                # Styles globaux

  config/                    # Fichiers YAML de config (modem, réponses...)
  docs/                      # Documentation (ARCHITECTURE, OSINT, etc.)
  logs/                      # Logs backend
  vocalguard.db              # Base SQLite de développement
  requirements.txt           # Dépendances racine (backend)
  README.md                  # Ce fichier
```

## Documentation

- [Guide d'installation](docs/INSTALLATION.md)
- [Architecture v3 (backend + frontend)](docs/ARCHITECTURE_V3.md)
- [Architecture v2 (améliorée)](docs/ARCHITECTURE_V2.md) - historique
- [Architecture originale](docs/ARCHITECTURE.md) - historique
- [Module OSINT](docs/OSINT.md) - Enrichissement des numéros de téléphone
- [Page Appels et OSINT](docs/APPELS_OSINT_UI.md) - Liste des appels, filtres, recherche intelligente
- [Services de réputation](docs/REPUTATION_SERVICES.md) - NOMOROBO / SHOULDIANSWER (type callattendant)
- [Résumé des améliorations](docs/IMPROVEMENTS_SUMMARY.md)
- [Améliorations par rapport à callattendant](docs/IMPROVEMENTS.md)

## API

Une fois l'application lancée, accédez à :
- **API Documentation** : http://localhost:8000/docs
- **API Alternative** : http://localhost:8000/redoc
- **Health Check** : http://localhost:8000/health

## Exemples d'utilisation

### Lister les appels

```bash
curl http://localhost:8000/api/v1/calls
```

### Ajouter un appelant à la liste blanche

```bash
curl -X POST http://localhost:8000/api/v1/callers \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+33123456789", "is_whitelisted": true}'
```

### Récupérer les messages vocaux

```bash
curl http://localhost:8000/api/v1/voicemails
```

### Enrichir un numéro via OSINT

```bash
curl http://localhost:8000/api/v1/osint/phone/+33123456789
```

### Vérifier la réputation d'un numéro

```bash
curl http://localhost:8000/api/v1/osint/reputation/+33123456789
```

## Développement

### Structure du projet

Le projet suit une architecture modulaire avec patterns modernes :
- `backend/core/` : Cœur du système (modem, gestion d'appels, événements)
- `backend/repositories/` : Pattern Repository pour l'accès aux données
- `backend/services/` : Couche Service pour la logique métier
- `backend/voice/` : Module vocal (reconnaissance et synthèse)
- `backend/api/` : API REST FastAPI avec dependency injection
- `backend/database/` : Modèles et gestion de base de données

Voir [ARCHITECTURE_V3.md](docs/ARCHITECTURE_V3.md) pour plus de détails sur l'architecture unifiée backend/frontend.

### Tests

```bash
pytest tests/
```

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou une pull request.

## Licence

MIT - Voir le fichier [LICENSE](LICENSE)

## Remerciements

Basé sur le projet [callattendant](https://github.com/emxsys/callattendant) de emxsys.

