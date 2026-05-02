# Service Telephony (daemon)

Processus dédié : modem, `CallManager`, routes `/api/v1/calls` (dont sortants), WebSocket `/ws/outgoing-call/{id}/audio`, relais des événements vers l’API principale.

**Documentation détaillée (split API / Pi, variables d’environnement, front)** : [docs/TELEPHONY_STACK.md](../../docs/TELEPHONY_STACK.md).

## Structure

| Module | Rôle |
|--------|------|
| `main.py` | Point d’entrée ASGI (`uvicorn backend.telephony_daemon.main:app`). |
| `settings.py` | `load_daemon_config()` → `Config` (YAML + env). |
| `factory.py` | Composition root : `create_telephony_app`, lifespan (DB + modem + tâche). |
| `relay.py` | `PublicApiEventRelay` : POST vers `/api/v1/internal/telephony-events`. |
| `relay_wiring.py` | Branche le relais sur `event_bus` une fois par processus. |
| `app.py` | Réexport de `create_telephony_app` (compat imports). |

## Déploiement seul

Même dépôt / même `Config` que l’API (base de données, secrets `TELEPHONY_*`). L’API doit exposer `POST /api/v1/internal/telephony-events` avec `TELEPHONY_INTERNAL_TOKEN`.

| Outil | Usage |
|--------|--------|
| `scripts/deploy_telephony.ps1` | Depuis le PC : archive, sync `.env.prod`, `pip`, systemd `vocalguard-telephony`, option `-RunTests` / `-RestartOnly`. |
| `scripts/run_telephony_daemon.sh` | Sur le Pi : lance uvicorn (bind `TELEPHONY_BIND_*`). |
| `scripts/run_telephony_tests.ps1` | **Unit** : pytest local. **RemoteSsh** : `smoke_telephony_stack.sh` sur le serveur (normalisation CRLF avant bash). **Endpoints** : HTTP vers `node11` ; POST interne avec `-FetchTokenFromRemote` ou `-InternalToken` si le token du PC ≠ `.env` du Pi. |
| `scripts/smoke_telephony_stack.sh` | Sur le serveur (répertoire app) : curl + pytest. |

Tests unitaires : `pytest backend/tests/test_telephony_pipeline.py backend/tests/telephony_daemon -q`.
