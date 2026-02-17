# Architecture VocalGuard v2 - Améliorée

## Vue d'ensemble

L'architecture de VocalGuard a été améliorée avec des patterns modernes pour une meilleure séparation des responsabilités, une extensibilité accrue et une maintenabilité améliorée.

## Principes architecturaux

### 1. Séparation des responsabilités (SoC)
- **Repositories** : Accès aux données
- **Services** : Logique métier
- **Controllers/API** : Gestion des requêtes HTTP
- **Core** : Composants système (modem, gestion d'appels)

### 2. Dependency Injection
- Injection de dépendances via FastAPI
- Facilite les tests unitaires
- Réduit le couplage entre composants

### 3. Event-Driven Architecture
- Système d'événements pour la communication découplée
- Composants peuvent réagir aux événements sans connaître les autres
- Facilite l'ajout de nouvelles fonctionnalités

### 4. Repository Pattern
- Abstraction de l'accès aux données
- Facilite le changement de base de données
- Code réutilisable pour les opérations CRUD

## Structure améliorée

```
VocalGuard/
├── vocalguard/
│   ├── core/                    # Cœur du système
│   │   ├── config.py            # Configuration
│   │   ├── events.py            # Système d'événements ✨ NOUVEAU
│   │   ├── modem_handler.py     # Gestion du modem
│   │   └── call_manager.py      # Gestion des appels (refactorisé)
│   │
│   ├── repositories/             # Pattern Repository ✨ NOUVEAU
│   │   ├── base.py              # Repository de base
│   │   ├── call_repository.py   # Repository des appels
│   │   ├── caller_repository.py  # Repository des appelants
│   │   ├── voicemail_repository.py  # Repository des messages vocaux
│   │   └── block_rule_repository.py # Repository des règles de blocage
│   │
│   ├── services/                # Couche métier ✨ NOUVEAU
│   │   ├── call_service.py      # Service de gestion des appels
│   │   └── block_service.py     # Service de blocage
│   │
│   ├── api/                     # API REST
│   │   ├── dependencies.py      # Injection de dépendances ✨ NOUVEAU
│   │   ├── routes/               # Routes API (refactorisées)
│   │   └── models.py             # Modèles Pydantic
│   │
│   ├── voice/                    # Module vocal
│   ├── database/                 # Base de données
│   └── main.py                  # Point d'entrée
```

## Composants principaux

### 1. Système d'événements (EventBus)

Permet une communication découplée entre composants :

```python
from vocalguard.core.events import EventBus, EventType, Event

# S'abonner à un événement
event_bus.subscribe(EventType.CALL_INCOMING, handle_incoming_call)

# Publier un événement
await event_bus.publish(Event(
    event_type=EventType.CALL_INCOMING,
    data={"phone_number": "+33123456789"}
))
```

**Avantages** :
- Découplage des composants
- Extensibilité facile
- Logging et monitoring centralisés

### 2. Repositories

Abstraction de l'accès aux données :

```python
from vocalguard.repositories.call_repository import CallRepository

repo = CallRepository(db)
call = repo.create_call(phone_number="+33123456789")
calls = repo.get_by_status("completed")
```

**Avantages** :
- Code réutilisable
- Facilite les tests (mocking)
- Changement de base de données simplifié

### 3. Services

Logique métier centralisée :

```python
from vocalguard.services.call_service import CallService

service = CallService(db)
call = await service.create_incoming_call(phone_number="+33123456789")
await service.answer_call(call.id)
```

**Avantages** :
- Logique métier centralisée
- Réutilisable par différents endpoints
- Facilite les tests

### 4. Dependency Injection

Injection de dépendances via FastAPI :

```python
from vocalguard.api.dependencies import get_call_service

@router.get("/calls")
async def get_calls(service: CallService = Depends(get_call_service)):
    return service.get_all()
```

**Avantages** :
- Testabilité améliorée
- Gestion du cycle de vie simplifiée
- Moins de couplage

## Flux de traitement amélioré

### Appel entrant

1. **ModemHandler** détecte l'appel → Publie `CALL_INCOMING`
2. **CallManager** reçoit l'événement → Crée l'appel via `CallService`
3. **CallService** crée l'appel → Publie `CALL_INCOMING`
4. **BlockService** vérifie si bloqué → Retourne le résultat
5. **CallManager** traite selon le résultat :
   - Si bloqué : `BlockService.block_call()` → Publie `CALL_BLOCKED`
   - Si autorisé : Interaction vocale → Publie `CALL_COMPLETED`

### Avantages de cette architecture

- **Découplage** : Chaque composant a une responsabilité claire
- **Testabilité** : Facile de mocker les dépendances
- **Extensibilité** : Ajouter de nouveaux handlers d'événements est simple
- **Maintenabilité** : Code organisé et facile à comprendre

## Patterns utilisés

### Repository Pattern
- Abstraction de l'accès aux données
- Facilite les tests et le changement de source de données

### Service Layer Pattern
- Logique métier séparée de l'accès aux données
- Réutilisable par différents endpoints

### Event-Driven Pattern
- Communication asynchrone et découplée
- Facilite l'ajout de nouvelles fonctionnalités

### Dependency Injection
- Injection de dépendances via FastAPI
- Facilite les tests unitaires

## Migration depuis v1

Les changements sont principalement internes :
- L'API reste compatible
- La configuration reste la même
- Les modèles de base de données sont inchangés

## Prochaines améliorations

- [ ] Tests unitaires avec mocks
- [ ] Middleware pour le logging automatique
- [ ] Validation avancée avec Pydantic
- [ ] Cache avec Redis
- [ ] Queue pour le traitement asynchrone
- [ ] Monitoring et métriques

