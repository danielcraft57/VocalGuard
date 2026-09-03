# Scripts PostgreSQL (node14)

Documentation complete : `docs/POSTGRES.md` (schema, cutover, perf, dump/restore).
Apercu prod : `docs/DEPLOYMENT_PROD.md` section configuration.

## Scripts

- `install_postgres_node14.sh` : apt, role/db, listen LAN, pg_hba scram, tuning Pi, `pg_stat_statements`
- `archive_sqlite.sh` : stop services, gzip backup, deplace le `.db`
- `cutover_node14.sh` : archive + `alembic upgrade head` + `DATABASE_URL` + restart + smoke
- `apply_perf_indexes.sh` : `alembic upgrade head` (indexes perf) + restart + smoke
- `fix_env_urls.sh` : aligne `.env` / `.env.prod` sur le mot de passe root-only
- `smoke_perf.sh` : verifie version Alembic, indexes cles, endpoints listes

## Ordre typique premiere installation

1. `sudo bash scripts/postgres/install_postgres_node14.sh`
2. Deployer le code VocalGuard sur `/opt/vocalguard`
3. `sudo bash scripts/postgres/cutover_node14.sh`
4. Apres maj code avec nouvelles migrations : `sudo bash scripts/postgres/apply_perf_indexes.sh`
