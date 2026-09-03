# PostgreSQL (VocalGuard)

Production sur **node14.lan** : PostgreSQL 17 a cote de l'API et du daemon telephonie.
Dev local : SQLite par defaut (`sqlite:///vocalguard.db`).

Doc deploiement courte aussi dans `DEPLOYMENT_PROD.md`. Scripts : `scripts/postgres/`.

## Decisions

- Schema **neuf** au cutover (pas d'import automatique de l'historique SQLite).
- JSON metier interdit. **Exception** : cues karaoke SRT en `JSONB`
  (`calls.transcription_cues`, `voicemails.transcription_cues`).
- Schema versionne avec **Alembic** (`alembic upgrade head`).
  En prod Postgres : pas de `create_all` runtime (sauf `VG_DB_AUTOCREATE=1`).

## Reseau / securite LAN

- `listen_addresses = localhost,<IP_LAN_node14>` (pas `*`)
- `pg_hba` : role `vocalguard` depuis `192.168.1.0/24` en `scram-sha-256`
- Mot de passe fort ; fichier root-only `/root/vocalguard_pg_password.txt` apres install
- UFW si present : 5432 seulement depuis le LAN
- SSL LAN : optionnel (prive) ; amelioration possible plus tard

Acces admin LAN :

```bash
psql -h node14.lan -U vocalguard -d vocalguard
```

Dump / restore :

```bash
pg_dump -U vocalguard vocalguard > dump.sql
psql -U vocalguard vocalguard < dump.sql
```

## URL applicative

Dans `.env` / `.env.prod` (non versionne) :

```text
DATABASE_URL=postgresql+psycopg2://vocalguard:<mdp>@127.0.0.1:5432/vocalguard
VG_DB_AUTOCREATE=0
```

Pool SQLAlchemy (Postgres) : `pool_size=10`, `max_overflow=20`, `pool_pre_ping`, `pool_recycle=1800`.

## Schema normalise (points cles)

- `calls` : colonnes a plat (`incoming_profile`, `no_message`, `ui_tag`, `ivr_intent`, …)
  + `transcription_cues` JSONB. L'API expose encore `extra_data` en **vue derivee** read-only.
- `quote_lines` : table enfant (remplace `quotes.lines` JSON)
- `callers` : plus de colonne JSON metadata
- `phone_number_profiles` : champs structures uniquement (plus de `raw_data`)

Migrations :

- `001_initial_pg` : schema initial
- `002_perf_indexes` : indexes chauds + extension `pg_trgm` (recherche entreprises)

Apres deploy code :

```bash
cd /opt/vocalguard
export DATABASE_URL=...
PYTHONPATH=/opt/vocalguard ./venv/bin/python -m alembic upgrade head
```

Ou `sudo bash scripts/postgres/apply_perf_indexes.sh` (upgrade + restart + smoke).

## Cutover SQLite -> Postgres (node14)

1. `sudo bash scripts/postgres/install_postgres_node14.sh`
2. Deployer le code (Alembic inclus)
3. `sudo bash scripts/postgres/cutover_node14.sh`
   (archive SQLite, `alembic upgrade head`, maj `DATABASE_URL`, restart services)
4. Smoke : `/health`, `/api/v1/calls`, login UI

Archive typique : `/opt/vocalguard/data/vocalguard.db.bak.<stamp>.gz`
et `.pre_postgres_<stamp>`.

## Perf pages (vs SQLite)

Objectif : listes et dashboard plus rapides que l'ancien SQLite.

- **Appels** : liste legere (pas de cues JSONB, transcription tronquee), OSINT
  via `normalized_number`, limit front ~100
- **Entreprises** : `selectinload` categories/emails, indexes trigram sur name/city
- **Dashboard** : agregats / GROUP BY (plus de dizaines de COUNT en boucle)
- **Messages** : pagination SQL reelle
- **Agenda** : filtre `from_time` / `to_time` selon la vue calendrier
- **Clients / devis / filtrage** : pagination + indexes booléens callers

Smoke rapide : `scripts/postgres/smoke_perf.sh`

## Scripts

Voir `scripts/postgres/README.md` :

- `install_postgres_node14.sh`
- `archive_sqlite.sh`
- `cutover_node14.sh`
- `apply_perf_indexes.sh`
- `fix_env_urls.sh`
- `smoke_perf.sh`
