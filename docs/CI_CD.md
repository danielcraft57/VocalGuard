# CI/CD VocalGuard

Ce projet inclut maintenant :

- **CI** : `.github/workflows/ci.yml`
  - backend: `pytest backend/tests`
  - frontend: `npm ci` + `npm run build`
- **CD prod** : `.github/workflows/cd-prod.yml`
  - déclenché sur push `master`
  - connexion SSH au serveur de prod
  - exécution `scripts/prod_auto_update.sh`

## Secrets GitHub requis

Dans `Settings > Secrets and variables > Actions` :

- `PROD_HOST` : host SSH du serveur app (ex: `node11.lan`)
- `PROD_USER` : utilisateur SSH (ex: `pi`)
- `PROD_SSH_KEY` : clé privée SSH (format OpenSSH)

Optionnel pour email custom en cas d'échec CD :

- `SMTP_SERVER`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_TO`
- `ALERT_EMAIL_FROM` (optionnel)

## Auto-update via cron (fallback / complément)

Si tu veux aussi une vérification périodique côté serveur (même sans push GitHub), installe le cron :

```bash
cd /opt/vocalguard
chmod +x scripts/prod_auto_update.sh scripts/install_prod_autoupdate_cron.sh
APP_DIR=/opt/vocalguard BRANCH=master SCHEDULE="*/5 * * * *" bash scripts/install_prod_autoupdate_cron.sh
```

Le log est écrit dans :

- `/opt/vocalguard/logs/auto_update.log`

## Notifications mail GitHub

Tu reçois déjà des emails GitHub si les notifications sont actives :

1. `GitHub > Settings > Notifications`
2. cocher les emails pour `Actions` / `Pull requests` selon ton besoin
3. dans le repo: `Watch > Custom > Actions`

Pas besoin d’un script mail séparé si la config GitHub est activée.  
Le mail SMTP dans le workflow reste une option supplémentaire.
