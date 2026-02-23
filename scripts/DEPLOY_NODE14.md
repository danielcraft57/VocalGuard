# Deploiement sur votre-rpi

Guide rapide pour deployer VocalGuard sur `pi@votre-rpi`.

## Pre-requis

- SSH configure vers `pi@votre-rpi` (cle SSH ou mot de passe)
- Le Raspberry Pi doit avoir Python 3.9+ et pip installes

## Etape 1 : Build du frontend (Windows)

Depuis la racine du projet VocalGuard :

```powershell
.\scripts\build_and_copy_frontend.ps1
```

Cela compile le frontend Next.js et copie le resultat dans `backend/web/`.

## Etape 2 : Deploiement sur votre-rpi

### Option A : Bash (WSL ou Git Bash)

```bash
RPI_HOST=pi@votre-rpi ./scripts/deploy_to_rpi.sh
```

### Option B : PowerShell

```powershell
$env:RPI_HOST="pi@votre-rpi"
.\scripts\deploy_to_rpi.ps1
```

Ou directement :

```powershell
.\scripts\deploy_to_rpi_simple.ps1
# Puis saisir : pi@votre-rpi
```

## Etape 3 : Lancer sur votre-rpi

SSH sur le Raspberry Pi, puis depuis `~/VocalGuard` :

```bash
ssh pi@votre-rpi
cd ~/VocalGuard
source venv/bin/activate
./run_backend.sh
```

Le script `run_backend.sh` definit `PYTHONPATH` et lance `uvicorn backend.main:app` pour eviter l'erreur `No module named 'backend'`.

En arriere-plan :

```bash
mkdir -p logs
nohup ./run_backend.sh > logs/vocalguard.log 2>&1 &
```

## Etape 4 : Acceder a l'interface

- Frontend : http://votre-rpi.local:8000/ (ou IP du RPi)
- API docs : http://votre-rpi.local:8000/docs

## Mise en production (service systemd)

Pour faire tourner VocalGuard en permanence (redemarrage auto, demarrage au boot) :

```bash
cd ~/VocalGuard
chmod +x scripts/install_service_rpi.sh
./scripts/install_service_rpi.sh
sudo systemctl start vocalguard
```

Voir **docs/DEPLOYMENT_PROD.md** pour les details (logs, config, depannage).

## Troubleshooting

- **No module named 'backend'** : Utiliser `./run_backend.sh` (ou `PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0`) au lieu de `python -m backend.main`.
- **Erreur SSH** : Verifier que `ssh pi@votre-rpi` fonctionne manuellement
- **Erreur Python** : Installer Python 3.9+ sur le RPi
- **Erreur build frontend** : Verifier que `npm run build` fonctionne localement
- **Port 8000 occupe** : Changer `api_port` dans la config ou tuer le processus existant
