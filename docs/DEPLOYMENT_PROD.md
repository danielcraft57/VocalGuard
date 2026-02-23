# Mise en production VocalGuard (Raspberry Pi)

Guide pour faire tourner VocalGuard en production sur un Raspberry Pi : service systemd, demarrage automatique, logs.

## Vue d'ensemble

- **Service systemd** : VocalGuard tourne comme un service, redemarre en cas de crash, demarre au boot.
- **Utilisateur** : par defaut `pi`, repertoire `~/VocalGuard`.
- **Port** : 8000 (modifiable dans le fichier service ou la config).

## 0. Prerequis systeme (Raspberry Pi)

Avant `pip install -r requirements.txt`, installer les paquets systeme pour compiler pyaudio (PortAudio) :

```bash
sudo apt-get update
sudo apt-get install -y python3-dev portaudio19-dev libasound2-dev
```

Voir [INSTALLATION.md](INSTALLATION.md) pour la liste complete.

## 1. Deployer le projet

Suivre [scripts/DEPLOY_NODE14.md](../scripts/DEPLOY_NODE14.md) (build frontend + `RPI_HOST=pi@votre-rpi ./scripts/deploy_to_rpi.sh`).

## 2. Installer le service systemd

Sur le Raspberry Pi, apres deploiement :

```bash
ssh pi@votre-rpi
cd ~/VocalGuard
chmod +x scripts/install_service_rpi.sh
./scripts/install_service_rpi.sh
```

Le script copie `vocalguard.service` dans `/etc/systemd/system/`, adapte le chemin et l'utilisateur, puis active le service au demarrage.

### Installation manuelle

Si le repertoire ou l'utilisateur differe (ex. `/opt/VocalGuard`, user `vocalguard`) :

```bash
# Editer vocalguard.service : WorkingDirectory, User, Group, PATH, PYTHONPATH, ExecStart
sudo cp vocalguard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vocalguard
```

## 3. Demarrer / arreter / redemarrer

```bash
sudo systemctl start vocalguard    # Demarrer
sudo systemctl stop vocalguard     # Arreter
sudo systemctl restart vocalguard  # Redemarrer
sudo systemctl status vocalguard   # Statut
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
- **Variables d'environnement** : optionnellement mettre un `.env` dans `~/VocalGuard` (base de donnees, cles API, etc.). Le service n'expose pas d'env par defaut ; pour en ajouter, editer le fichier service et ajouter des lignes `Environment=...`.
- **Base de donnees** : SQLite par defaut (`vocalguard.db` dans le repertoire du projet). Pour PostgreSQL en prod, definir `database_url` dans la config.

## 7. Fichiers concernes

| Fichier | Role |
|--------|------|
| `vocalguard.service` | Unite systemd (ExecStart, User, WorkingDirectory, restart) |
| `scripts/install_service_rpi.sh` | Installation et activation du service sur le RPi |
| `run_backend.sh` | Lancement manuel (dev ou debug) |

## 8. Depannage

- **Le service ne demarre pas** : `journalctl -u vocalguard -n 50` pour voir l'erreur. Verifier que `PYTHONPATH` et `WorkingDirectory` pointent bien vers le projet et que le venv existe.
- **Port 8000 deja utilise** : changer le port dans `ExecStart` (ex. `--port 8080`) ou liberer le port.
- **Droits** : le service tourne sous l'utilisateur `pi` ; fichiers et repertoires du projet doivent etre lisables par cet utilisateur.
