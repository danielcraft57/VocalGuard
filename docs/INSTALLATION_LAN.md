# Installation stack LAN VocalGuard (node14 + node15)

Guide de reference pour une installation **production** sur deux Raspberry Pi (telephonie + services voix/OSINT). Pour le dev PC local, voir [INSTALLATION.md](INSTALLATION.md).

## Vue d'ensemble

| Hote | Role | Services principaux | Ports |
|------|------|---------------------|-------|
| **node14** | API, modem, base, files d'attente | `vocalguard`, `vocalguard-telephony`, `vocalguard-celery`, `vocalguard-celery-beat`, PostgreSQL, Redis | 8000 (API), 8090 (telephony), 5432, 6379 |
| **node15** | STT/TTS Whisper, OSINT PhoneInfoga | `vocalguard-stt` (+ `vocalguard-whisper` selon install), `vocalguard-osint`, ProspectLab (optionnel) | 8100 (STT), 8110 (OSINT) |
| **node12** (optionnel) | Nginx TLS / reverse proxy | `nginx` | 443 |

Le code applicatif est deploye sous `/opt/vocalguard` sur node14. Le worker OSINT vit sous `/opt/vocalguard-osint` sur node15, le daemon STT sous `/opt/vocalguard-stt`.

```
                    navigateur / mobile
                              |
                    node12 (nginx) optionnel
                              |
                         node14 :8000
                    API + front statique backend/web
                              |
              +---------------+---------------+
              |                               |
      node14 :8090                      node15
   telephony_daemon                  :8100 STT
   (modem USB)                       :8110 OSINT
              |
         PostgreSQL + Redis (node14)
```

Documentation connexe :

- Deploiement scripts : [../scripts/DEPLOY_NODE14.md](../scripts/DEPLOY_NODE14.md), [DEPLOYMENT_PROD.md](DEPLOYMENT_PROD.md)
- Modem et daemon : [TELEPHONY_STACK.md](TELEPHONY_STACK.md)
- OSINT detail : [OSINT.md](OSINT.md)
- STT / conversation : [VOICE_NODE15.md](VOICE_NODE15.md)
- PostgreSQL : [POSTGRES.md](POSTGRES.md)

---

## 1. Prerequis communs

### Materiel (node14)

- Raspberry Pi 3B+ ou mieux, alimentation stable USB pour le modem
- Modem USB (ex. US Robotics 56K, voir [MODEM_USR5637.md](MODEM_USR5637.md))
- Cablage ligne : filtre ADSL / prise gigogne, telephone en parallele, modem sur sortie voix du filtre ([TELEPHONY_STACK.md](TELEPHONY_STACK.md))

### Paquets systeme (node14)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-dev \
  portaudio19-dev libasound2-dev ffmpeg postgresql redis-server
```

Droits modem :

```bash
sudo usermod -aG dialout pi
# Symlink conseille (udev ou deploy) : /dev/modem56k -> ttyACM0
```

### Paquets systeme (node15)

Python 3, venv, curl, build-essential si compilation whisper.cpp (voir `scripts/deploy_stt.ps1`).

---

## 2. node14 : application et donnees

### 2.1 Deploiement initial

Depuis le PC de dev (PowerShell) :

```powershell
.\scripts\deploy_to_rpi.ps1 -AppServerName node14.lan -AppServerUser pi `
  -RestartService -HealthCheck
```

Sans front : ajouter `-SkipFrontendBuild` (non recommande en prod).

Variables utiles : voir `.env.prod.example` a la racine du depot. Sur le Pi :

- `.env.prod` : source de verite prod (non versionne)
- `.env` : copie utilisee par systemd au boot (`deploy_to_rpi.ps1` synchronise `.env.prod` vers `.env`)

`VG_ENV=prod` doit etre present (ajoute par le script de deploiement si absent).

### 2.2 PostgreSQL

Installation et migration : [POSTGRES.md](POSTGRES.md).

Dans `.env` / `.env.prod` :

```text
DATABASE_URL=postgresql+psycopg2://vocalguard:<mot_de_passe>@127.0.0.1:5432/vocalguard
```

Schema : `alembic upgrade head` depuis `/opt/vocalguard` (souvent integre au deploy).

### 2.3 Redis et Celery

Redis sert de **broker** et **result backend** pour Celery (taches OSINT, agenda, etc.).

**Configuration recommandee sur node14** (API et workers sur le meme hote) :

```text
CELERY_BROKER_URL=redis://127.0.0.1:6379/2
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2
```

Important :

- Les unites systemd `vocalguard-celery` et `vocalguard-celery-beat` chargent `EnvironmentFile=-/opt/vocalguard/.env`, **pas** seulement `.env.prod`. Toute modification de Redis doit etre refletee dans **les deux** fichiers, ou assurez-vous que le deploy recopie `.env.prod` vers `.env`.
- N'utilisez pas `redis://node14.lan:6379/...` si Redis est configure pour ecouter uniquement sur `127.0.0.1` (connexion refusee, worker en boucle, OSINT non planifie).

**Redis : stabilite au boot**

Erreur typique : `Could not create server TCP listening socket 192.168.x.x:6379: bind: Cannot assign requested address` si Redis demarre avant que l'interface LAN soit prete.

Correctif recommande :

```bash
# /etc/redis/redis.conf
bind 127.0.0.1 -::1

# Attente reseau (drop-in systemd)
sudo mkdir -p /etc/systemd/system/redis-server.service.d
printf '%s\n' '[Unit]' 'After=network-online.target' 'Wants=network-online.target' \
  | sudo tee /etc/systemd/system/redis-server.service.d/network.conf
sudo systemctl daemon-reload
sudo systemctl restart redis-server
```

Memoire (evite warnings Celery / persist Redis) :

```bash
echo 'vm.overcommit_memory = 1' | sudo tee /etc/sysctl.d/99-vocalguard-redis.conf
sudo sysctl -p /etc/sysctl.d/99-vocalguard-redis.conf
```

Verification :

```bash
systemctl is-active redis-server
redis-cli ping
```

### 2.4 Services systemd node14

| Unite | Role |
|-------|------|
| `vocalguard.service` | API FastAPI + front statique `backend/web/` (port 8000) |
| `vocalguard-telephony.service` | Daemon modem, appels, WebSocket audio sortant (port 8090) |
| `vocalguard-celery.service` | Worker taches async (OSINT, etc.) |
| `vocalguard-celery-beat.service` | Planificateur Celery |

Activer au boot :

```bash
sudo systemctl enable vocalguard vocalguard-telephony vocalguard-celery vocalguard-celery-beat
```

Variables telephonie (voir `.env.prod.example`) :

```text
USE_TELEPHONY_DAEMON=1
TELEPHONY_DAEMON_URL=http://127.0.0.1:8090
TELEPHONY_PUBLIC_API_URL=http://127.0.0.1:8000
TELEPHONY_INTERNAL_TOKEN=<secret_partage_api_et_daemon>
```

L'API relaie les evenements WebSocket via `POST /api/v1/internal/telephony-events` (header `X-VocalGuard-Internal`).

Deploiement cible telephonie seule : `.\scripts\deploy_telephony.ps1 -AppServerName node14.lan`

### 2.5 Interface web (session)

En prod LAN, definir au minimum :

```text
VG_UI_PASSWORD=<mot_de_passe_interface>
```

Sans session UI, les endpoints `/api/v1/calls` renvoient `Session UI requise.`

### 2.6 Voix prod : ElevenLabs (accueil) + node15 (STT), pas Edge sur le Pi

**Accueil entrant (modem)** : regle par `data/incoming_call_settings.yaml` (ou UI **Parametres → Accueil audio**) avec `tts_provider: elevenlabs` par audience (known / unknown / commercial). Sur node14 seulement :

```text
ELEVENLABS_API_KEY=<cle>
# ELEVENLABS_VOICE_ID=...   optionnel si defini dans le YAML
```

Regenere les WAV apres changement : `python scripts/regenerate_all_greetings_pi.py` (telephonie arretee) ou bouton **Regenerer** dans l'UI.

**Ne pas compter sur Edge TTS sur le Raspberry** : Microsoft renvoie souvent 403 (websocket). Les fallbacks Edge locaux ne doivent pas etre la strategie prod.

**`TTS_SERVICE_URL`** (node15) : optionnel, utile surtout pour le **mode conversation**, le prefetch KB et les anciens flux `greeting-mix` Edge. Quand `tts_provider=elevenlabs` sur l'accueil, le mix accueil est fait **sur node14** (ElevenLabs + jingle), **sans** passer par node15.

### 2.7 STT distant (node15)

Dans `.env.prod` sur node14 (fichiers **LF**, pas CRLF Windows) :

```text
STT_SERVICE_URL=http://node15.lan:8100
VOICE_STT_LOCAL_FALLBACK=0
STT_INTERNAL_TOKEN=<meme valeur que /opt/vocalguard-stt/.env.stt sur node15>
```

Apres chaque `deploy_stt.ps1`, **recopier le token** affiche en fin de script (ou `grep STT_INTERNAL_TOKEN` sur node15) dans `.env` **et** `.env.prod` sur node14, puis redemarrer `vocalguard`, `vocalguard-telephony`, `vocalguard-celery`.

Sans STT joignable : messagerie possible mais transcription vide ; voir logs telephony.

---

## 3. node15 : STT et OSINT

### 3.0 Reinstallation rapide (node15)

Depuis le PC de dev (PowerShell), dans l'ordre :

```powershell
.\scripts\deploy_stt.ps1 -SttServerName node15.lan
.\scripts\deploy_osint_node15.ps1 -OsintServerName node15.lan
```

Puis sur **node14** : aligner `STT_INTERNAL_TOKEN` et `OSINT_INTERNAL_TOKEN`, redemarrer l'API + Celery + telephonie (voir sections 2.7 et 3.2).

Verification locale sur node15 :

```bash
systemctl is-active vocalguard-whisper vocalguard-stt vocalguard-osint
curl -sS http://127.0.0.1:8101/ | head -c 80
curl -sS http://127.0.0.1:8100/health
curl -sS http://127.0.0.1:8110/health
```

### 3.1 Service STT (Whisper)

Depuis le PC :

```powershell
.\scripts\deploy_stt.ps1 -SttServerName node15.lan
```

Service : `vocalguard-stt` (port **8100**), souvent avec `vocalguard-whisper` pour whisper-server local.

Test depuis node14 :

```bash
curl -sS http://node15.lan:8100/health
```

Aligner `STT_INTERNAL_TOKEN` entre node14 `.env` et node15 `/opt/vocalguard-stt/.env.stt` si l'authentification est activee.

Unites systemd : `vocalguard-whisper` (whisper-server **127.0.0.1:8101**) + `vocalguard-stt` (FastAPI **0.0.0.0:8100**, auth Bearer).

Details conversation / TTS distant (hors accueil ElevenLabs) : [VOICE_NODE15.md](VOICE_NODE15.md).

### 3.2 Worker OSINT (PhoneInfoga)

Deploy initial :

```powershell
.\scripts\deploy_osint_node15.ps1 -OsintServerName node15.lan
```

Le script :

- installe `/opt/vocalguard-osint` (venv, binaire PhoneInfoga arm64)
- ecrit `/opt/vocalguard-osint/.env.osint` avec `OSINT_INTERNAL_TOKEN`
- installe et **demarre** `vocalguard-osint.service` (port **8110**)

Sur **node14**, dans `.env.prod` et `.env` :

```text
OSINT_SERVICE_URL=http://node15.lan:8110
OSINT_INTERNAL_TOKEN=<meme_valeur_que_/opt/vocalguard-osint/.env.osint>
```

**Le token doit etre strictement identique** sur les deux hotes. Un token different provoque `401 Unauthorized` sur `POST /v1/scan` et l'UI n'affiche qu'un enrichissement local (detecteur FR).

Activer au boot (si le service a ete installe mais reste arrete) :

```bash
sudo systemctl enable vocalguard-osint
sudo systemctl start vocalguard-osint
```

Verifications :

```bash
# sur node15
systemctl is-active vocalguard-osint
curl -sS http://127.0.0.1:8110/health

# depuis node14
curl -sS http://node15.lan:8110/health
```

Puis sur node14 :

```bash
sudo systemctl restart vocalguard vocalguard-celery
```

Relance OSINT pour un numero connu (apres session UI ou via tache Celery) :

```text
POST /api/v1/calls/{call_id}/osint/queue
```

---

## 4. Check-list post-installation

### node14

```bash
systemctl is-active postgresql redis-server vocalguard vocalguard-telephony vocalguard-celery vocalguard-celery-beat
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8090/health
test -f /opt/vocalguard/backend/web/index.html
grep CELERY_BROKER_URL /opt/vocalguard/.env
```

Le JSON `GET /health` doit indiquer `telephony_daemon_reachable: true` et `modem_initialized: true` si le modem est branche.

### node15

```bash
systemctl is-active vocalguard-whisper vocalguard-stt vocalguard-osint
curl -sS http://127.0.0.1:8100/health
curl -sS http://127.0.0.1:8110/health
```

### Depuis le PC (smoke)

```powershell
.\scripts\run_telephony_tests.ps1
```

Ou sur le Pi : `bash /opt/vocalguard/scripts/smoke_telephony_stack.sh`

---

## 5. Depannage courant

### Liste Appels vide ou sans OSINT / messagerie

1. **Redis** : `systemctl status redis-server` ; `redis-cli ping`
2. **Celery** : `tail -n 40 /opt/vocalguard/logs/vocalguard-celery.log` (chercher `Cannot connect to redis`)
3. **URLs Celery** : doivent pointer `127.0.0.1`, pas le hostname, si Redis ecoute en local uniquement
4. **OSINT distant** : service actif sur node15, token identique, `curl node15:8110/health`
5. **Appels sans numero** : logs telephony `CID decision cause=timeout` (operateur / cablage CID)
6. **Pas de message vocal** : `repondeur_sans_parole` (appelant silencieux ou VAD : `last_vrx_heard_speech=false`)
7. **Appel manque** : `Impossible de decrocher au RING` / `seize_ok=0` (modem, timing RING, conflit USB)

### WebSocket temps reel (modale appel entrant)

- Front servi par l'API (same-origin) : pas de token WS
- Domaine public via nginx : verifier proxy WebSocket vers 8000
- Evenements daemon : `TELEPHONY_INTERNAL_TOKEN` + relais `relay_successes` dans health telephony

### Redis en echec permanent au boot

Voir section 2.3 (bind loopback + drop-in `network-online`).

### STT 401 sur node15 (`/v1/transcribe`, `/v1/tts`)

`STT_INTERNAL_TOKEN` sur node14 different de `/opt/vocalguard-stt/.env.stt` sur node15. Aligner puis redemarrer les services (section 2.7).

### Deploy : erreurs `cd: /opt/vocalguard\r` ou `set: - invalid option`

Fichiers `.env.prod` ou scripts copies depuis Windows avec fins de ligne **CRLF**. Convertir en LF sur le PC (`dos2unix` ou editeur) avant deploy, notamment `.env.prod` a la racine du depot.

### OSINT 401 depuis node14

Comparer :

```bash
grep OSINT_INTERNAL_TOKEN /opt/vocalguard/.env
grep OSINT_INTERNAL_TOKEN /opt/vocalguard-osint/.env.osint   # sur node15
```

Corriger, puis `sudo systemctl restart vocalguard-osint` et `sudo systemctl restart vocalguard-celery`.

### Modem : Input/output error

```bash
journalctl -u vocalguard-telephony -n 80
ls -la /dev/modem56k /dev/ttyACM0
sudo systemctl restart vocalguard-telephony
```

Verifier cable USB, alimentation, eviter que ModemManager ne monopolise le port (desactiver ou regle udev si besoin).

---

## 6. Fichiers et scripts utiles

| Fichier / script | Usage |
|------------------|--------|
| `.env.prod.example` | Modele variables prod |
| `scripts/deploy_to_rpi.ps1` | Deploy complet node14 |
| `scripts/deploy_telephony.ps1` | Daemon modem seul |
| `scripts/deploy_stt.ps1` | STT node15 |
| `scripts/deploy_osint_node15.ps1` | OSINT node15 |
| `scripts/regenerate_all_greetings_pi.py` | Regen accueils ElevenLabs (node14, telephony off) |
| `scripts/postgres/` | Install / cutover Postgres |
| `scripts/systemd/vocalguard-osint.service` | Unite OSINT node15 |
| `scripts/smoke_telephony_stack.sh` | Smoke test API + daemon |

---

## 7. Ordre d'installation recommande (nouveau site)

1. PostgreSQL + Redis sur node14 (conf Redis stable)
2. Deploy `deploy_to_rpi.ps1` (code, venv, `.env.prod`, systemd API + Celery)
3. Deploy telephony `deploy_telephony.ps1` + test modem
4. Deploy STT node15 + `STT_SERVICE_URL` sur node14
5. Deploy OSINT node15 + `OSINT_SERVICE_URL` et token sur node14
6. `alembic upgrade head`, redemarrer toute la stack node14
7. Check-list section 4 + appel test entrant