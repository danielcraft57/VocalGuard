# Deploiement prod (app + nginx)

Guide court pour deployer VocalGuard en prod avec:
- application/backend sur `pi@app-node.lan`
- reverse proxy Nginx sur `pi@edge-node.lan`

## Pre-requis

- SSH fonctionnel vers `pi@app-node.lan` (app) et `pi@edge-node.lan` (nginx)
- PowerShell + `ssh/scp/tar` disponibles localement
- fichier local `.env.prod` renseigne (copie vers `.env` sur le serveur)

## Script unique

Le script unique de deploiement est :

```powershell
.\scripts\deploy_to_rpi.ps1
```

Par défaut, il cible:
- app: `pi@app-node.lan`
- nginx: `pi@edge-node.lan`
- dossier app: `/opt/vocalguard`

Options utiles :

```powershell
.\scripts\deploy_to_rpi.ps1 -AppServerUser "pi" -AppServerName "app-node.lan" -NginxServerUser "pi" -NginxServerName "edge-node.lan" -RestartService -ConfigureNginx
.\scripts\deploy_to_rpi.ps1 -SkipFrontendBuild
.\scripts\deploy_to_rpi.ps1 -NoSystemDeps
.\scripts\deploy_to_rpi.ps1 -ConfigureNginx -RestartService -HealthCheck
.\scripts\deploy_to_rpi.ps1 -RemoteDir "/opt/vocalguard"
.\scripts\deploy_to_rpi.ps1 -ConfigureNginx -EnableHttps -CertbotEmail "admin@exemple.fr" -HealthCheck
.\scripts\deploy_to_rpi.ps1 -ConfigureNginx -FixNginxLegacyWarnings -HealthCheck
```

Par défaut, le script publie aussi les alias de domaine suivants côté Nginx:
- `vocalguard.danielcraft.fr`
- `phone.danielcraft.fr`
- `repondeur.danielcraft.fr`

Tu peux surcharger avec `RPI_DOMAIN_ALIASES` (liste CSV) ou `-DomainAliases`.

## Ce que fait le script

1. Verifie la connexion SSH.
2. Build le frontend et copie dans `backend/web` (sauf `-SkipFrontendBuild`).
3. Prepare le serveur (dossier, venv, deps systeme utiles).
Le script gere automatiquement les droits sur `/opt/vocalguard`:
- `sudo mkdir -p /opt/vocalguard`
- `sudo chown -R <user>:<user> /opt/vocalguard`
- `chmod` dossiers/fichiers pour execution et ecriture runtime.
4. Synchronise le code (archive optimisee).
5. Applique `.env.prod` -> `.env` sur le serveur avec backup auto.
6. Ajoute `VG_ENV=prod` si absent.
7. Installe/met a jour les dependances Python.
8. Optionnel: restart `vocalguard` via systemd (`-RestartService`).
9. Optionnel: configure/reload Nginx (`-ConfigureNginx`) sur le noeud edge, proxy vers app-node:8000.
10. Optionnel: health checks automatiques (`-HealthCheck`) backend + nginx.

## Verification rapide sur le Pi

```bash
ssh pi@app-node.lan
cd ~/VocalGuard
source venv/bin/activate
grep '^DATABASE_URL=' .env
curl http://localhost:8000/health

ssh pi@edge-node.lan
curl -I http://edge-node.lan
```

## Remarques prod

- `DATABASE_URL` doit pointer vers PostgreSQL en prod (`postgresql+psycopg2://...`).
- Le script preserve les donnees runtime (`venv`, `logs`, `data`, `recordings`).
- Voir `docs/DEPLOYMENT_PROD.md` pour la partie service systemd.
