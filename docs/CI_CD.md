# CI/CD VocalGuard

Ce projet inclut maintenant :

- **CI** : `.github/workflows/ci.yml`
  - backend: `pytest backend/tests`
  - frontend: `npm ci` + `npm run build`
- **CD prod** : `.github/workflows/cd-prod.yml`
  - déclenché sur push `master`
  - mode **pull-based** (pas de SSH direct depuis GitHub)
  - le serveur met à jour via `scripts/prod_auto_update.sh` (cron)

## Pourquoi pas de SSH direct GitHub -> node11.lan ?

`node11.lan` est un hostname privé LAN, inaccessible depuis les runners GitHub hébergés.
Donc la stratégie fiable est :

1. merge sur `master`
2. workflow CI/CD valide le push
3. cron sur `node11` fait `fetch/pull + restart`

## Secrets GitHub (optionnels)

Aucun secret n'est requis pour le mode pull-based.

Optionnel uniquement pour des mails custom :

- `SMTP_SERVER`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_TO`
- `ALERT_EMAIL_FROM` (optionnel)

Script d'aide (local) :

```bash
bash scripts/setup_github_secrets.sh
```

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
