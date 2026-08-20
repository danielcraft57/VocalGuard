# Téléphonie : API principale + daemon (modem)

Deux rôles possibles :

| Processus | Rôle |
|-----------|------|
| **API FastAPI** (`backend.main` / `backend.api.app`) | REST, WebSocket `/ws/events`, ingestion `POST /api/v1/internal/telephony-events`, proxy HTTP vers le daemon pour les appels sortants si `USE_TELEPHONY_DAEMON=1`. |
| **Daemon téléphonie** (`backend.telephony_daemon.main`, port **8090** par défaut) | Modem série, `CallManager`, sessions sortantes, WebSocket **`/ws/outgoing-call/{id}/audio`**, relais des événements bus → API via POST interne. |

Sur une même machine (ex. Raspberry Pi), les deux peuvent coexister avec `TELEPHONY_DAEMON_URL=http://127.0.0.1:8090`.

## Variables d’environnement (résumé)

| Variable | Où | Rôle |
|----------|-----|------|
| `USE_TELEPHONY_DAEMON` | API principale | `1` : pas d’ouverture du modem dans ce processus ; proxification des routes sortantes vers `TELEPHONY_DAEMON_URL`. **Sur le service `vocalguard-telephony`, cette valeur est ignorée** (le daemon traite toujours les appels en local). |
| `TELEPHONY_DAEMON_URL` | API principale | URL du daemon (ex. `http://node14.lan:8090`). |
| `TELEPHONY_PUBLIC_API_URL` | **Daemon** | URL joignable **depuis le Pi** vers l’API qui reçoit les événements (ex. `http://192.168.x.x:8000` si l’API tourne sur un PC). |
| `TELEPHONY_INTERNAL_TOKEN` | API + daemon | Même secret pour l’en-tête `X-VocalGuard-Internal` sur `/internal/telephony-events`. |
| `TELEPHONY_BIND_HOST` / `TELEPHONY_BIND_PORT` | Daemon | Écoute (souvent `0.0.0.0:8090` sur le réseau local). |
| `TELEPHONY_RELAY_WARN_INTERVAL_SEC` | Daemon (optionnel) | Limite la fréquence des logs d’échec du relais HTTP (défaut 30 s). |

## Développement : PC Windows + modem sur le Pi

1. **Backend local** : `USE_TELEPHONY_DAEMON=1`, `TELEPHONY_DAEMON_URL=http://<pi>:8090`.  
   L’API locale **ne tente plus** d’ouvrir `/dev/ttyACM0` dans ce mode.

2. **Frontend** : pour entendre la ligne dans le navigateur, la session audio vit sur le daemon. Définir dans `frontend/.env.local` :
   ```env
   NEXT_PUBLIC_TELEPHONY_WS_BASE=ws://node14.lan:8090
   ```
   (`NEXT_PUBLIC_*` : redémarrer `next dev` après modification.)

3. **Jeton** : `TELEPHONY_INTERNAL_TOKEN` aligné entre `.env` local et `.env` du Pi pour les POST internes.

## Déploiement daemon seul

```powershell
.\scripts\deploy_telephony.ps1 -AppServerName node14.lan
```

Synchronise le dépôt, copie `.env.prod` → `.env` distant, `pip`, service `vocalguard-telephony`.

## Vérifications HTTP

- Script portable : `python scripts/test_api_stack.py` (racine du dépôt).
- PowerShell : `.\scripts\run_telephony_tests.ps1 -Mode Stack -RemoteHost node14.lan`

Voir aussi `backend/telephony_daemon/README.md` et `scripts/smoke_telephony_stack.sh` (sur le serveur Linux).
