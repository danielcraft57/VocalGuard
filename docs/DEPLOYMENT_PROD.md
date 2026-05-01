# Mise en production VocalGuard (Raspberry Pi)

Guide pour faire tourner VocalGuard en production sur un Raspberry Pi : service systemd, demarrage automatique, logs.

## Vue d'ensemble

- **Service systemd** : VocalGuard tourne comme un service, redemarre en cas de crash, demarre au boot.
- **Utilisateur** : configurable (ex: `pi`), repertoire deploiable (ex: `/opt/vocalguard`).
- **Port** : 8000 (modifiable dans le fichier service ou la config).

## 0. Prerequis systeme (Raspberry Pi)

Avant `pip install -r requirements.txt`, installer les paquets systeme pour compiler pyaudio (PortAudio) :

```bash
sudo apt-get update
sudo apt-get install -y python3-dev portaudio19-dev libasound2-dev
```

Voir [INSTALLATION.md](INSTALLATION.md) pour la liste complete.

## 1. Deployer le projet

Suivre [scripts/DEPLOY_NODE14.md](../scripts/DEPLOY_NODE14.md) et lancer le script unique:
`pwsh -File ./scripts/deploy_to_rpi.ps1 -AppServerUser pi -AppServerName app-node.lan -NginxServerUser pi -NginxServerName edge-node.lan -ConfigureNginx`.

## 2. Installer/mettre a jour les services systemd

Le script de deploiement genere et installe automatiquement les unites systemd:
- `vocalguard.service` (API)
- `vocalguard-celery.service` (worker Celery)
- `vocalguard-frontend.service` (optionnel, Next.js standalone)
- `vocalguard-test-modem.service` (optionnel)

Exemple:

```powershell
.\scripts\deploy_to_rpi.ps1 `
  -AppServerUser "pi" -AppServerName "app-node.lan" `
  -NginxServerUser "pi" -NginxServerName "edge-node.lan" `
  -InstallServices $true -EnableFrontendService $false -EnableModemTestService $false `
  -ConfigureNginx -RestartService -HealthCheck
```

## 3. Demarrer / arreter / redemarrer

```bash
sudo systemctl start vocalguard    # Demarrer
sudo systemctl stop vocalguard     # Arreter
sudo systemctl restart vocalguard  # Redemarrer
sudo systemctl status vocalguard   # Statut
sudo systemctl status vocalguard-celery
```

## 4. Logs

```bash
journalctl -u vocalguard -f          # Suivre les logs en direct
journalctl -u vocalguard -n 100       # Dernieres 100 lignes
journalctl -u vocalguard --since "1 hour ago"
```

## 5. Demarrage automatique

Une fois le service active (`systemctl enable vocalguard`), VocalGuard demarre automatiquement au boot du Raspberry Pi.

## 6. Configuration production

- **Fichier de config** : `~/VocalGuard/config/config.yaml` (ou `~/.vocalguard/config.yaml` selon la config). Creer depuis `config/config.example.yaml` si besoin.
- **Variables d'environnement** : gerer en prod via un fichier local `.env.prod` (non versionne), copie vers `.env` sur le serveur par `deploy_to_rpi.ps1`.
  Le runtime charge `.env.prod` automatiquement quand `VG_ENV=prod`, sinon fallback `.env`.
- **Base de donnees** : SQLite par defaut (`vocalguard.db` dans le repertoire du projet). Pour PostgreSQL en prod, definir `DATABASE_URL` (ou `database_url`) avec des credentials non exposes.

## 7. Fichiers concernes

| Fichier | Role |
|--------|------|
| `scripts/deploy_to_rpi.ps1` | Deploiement complet + generation/installation des services systemd |
| `run_backend.sh` | Lancement manuel (dev ou debug) |

## 8. Depannage

- **Le service ne demarre pas** : `journalctl -u vocalguard -n 50` pour voir l'erreur. Verifier que `PYTHONPATH` et `WorkingDirectory` pointent bien vers le projet et que le venv existe.
- **Port 8000 deja utilise** : changer le port dans `ExecStart` (ex. `--port 8080`) ou liberer le port.
- **Droits** : le service tourne sous l'utilisateur `pi` ; fichiers et repertoires du projet doivent etre lisables par cet utilisateur.
