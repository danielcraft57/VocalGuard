# Qdrant intents (node15) - journal d'integration

Document de reference pour la BDD vectorielle des intents VocalGuard.
Installee **sans Docker** sur `pi@node15.lan`, integree au predict KB / STT / UI.

Cutover LAN : 2026-09-14. UI statut + source moteur : 2026-09-15 (restaure en repo 2026-09-24).

## Objectif

Accelerer la recherche d'intents (ANN cosine) en sortant le chemin chaud
de Postgres/pgvector (node14) vers Qdrant local sur node15, au plus pres
du service voix (`vocalguard-stt` :8100).

Postgres reste la source de verite metier (tags, patterns, responses, CRUD).
Qdrant stocke les vecteurs + payload leger pour la recherche.

## Architecture

```text
                    +------------------+
  UI / API node14   | Postgres node14  |  intents, patterns, responses,
  CRUD KB --------->| + pgvector       |  embedding_json (source)
                    +--------+---------+
                             | migrate / sync upsert
                             v
  node15 STT :8100  +------------------+
  intent-predict -->| Qdrant :6333     |  collection intents
  (QDRANT_URL)      | dim 384 Cosine   |  payload: intent_tag, ref_type, ref_id
                    +------------------+
```

Ordre de predict (`backend/services/intent_repository.py`) :

1. **Qdrant** si `QDRANT_URL` est defini et joignable
2. sinon **pgvector** SQL (`embedding <=>`)
3. sinon **cosine Python** sur `embedding_json`

Puis boost lexical `pattern_boost_scores` (toujours via Postgres).

L'API expose le moteur utilise via `source` / `vector_engine` :
`qdrant` | `pgvector` | `python` | `node15` | `empty`.

## Materiel / etat node15 (constate au cutover)

| Element | Valeur |
|---------|--------|
| Hote | `pi@node15.lan` (`raspberry-15`) |
| Arch | `aarch64` |
| Kernel page size | `16384` (Pi 5) |
| RAM | ~4 GiB |
| Qdrant | `1.19.1` binaire musl aarch64 |
| Install | `/opt/qdrant` |
| Storage | `/var/lib/qdrant/storage` |
| Service | systemd `qdrant` |
| HTTP | `0.0.0.0:6333` (gRPC 6334) |
| Collection | `intents` |
| Points | ~596-597 |
| STT | `/opt/vocalguard-stt`, health `qdrant_ok: true` |

Note Pi 5 : si le binaire officiel crash jemalloc (`Unsupported system page size`),
recompiler avec `JEMALLOC_SYS_WITH_LG_PAGE=14`. Le binaire musl `v1.19.1`
tourne correctement sur node15 tel quel.

## Installation Qdrant (sans Docker)

Script : `scripts/install_qdrant_node15.sh`

```bash
# Sur node15, depuis une copie du repo
bash scripts/install_qdrant_node15.sh
```

Fichiers associes :

- `scripts/qdrant/config.yaml` - storage / host / ports
- `scripts/systemd/qdrant.service` - unit systemd (`User=pi`)

Commandes utiles :

```bash
sudo systemctl status qdrant
curl -sS http://127.0.0.1:6333/
curl -sS http://127.0.0.1:6333/collections/intents
```

Dashboard : `http://node15.lan:6333/dashboard`

## Dependances Python

Dans `requirements.txt` :

```text
qdrant-client>=1.8.0,<2.0.0
```

Le client applicatif utilise surtout **httpx** (`backend/voice/qdrant_intents.py`).
`qdrant-client` est installe pour coherence / futurs usages.

`scripts/deploy_stt.ps1` doit conserver `QDRANT_URL` / `DATABASE_URL` dans `.env.stt`.

## Variables d'environnement

| Hote | Fichier | Cle | Valeur typique |
|------|---------|-----|----------------|
| node15 STT | `/opt/vocalguard-stt/.env.stt` | `QDRANT_URL` | `http://127.0.0.1:6333` |
| node15 STT | idem | `DATABASE_URL` | Postgres node14 (boost / fallback) |
| node14 API | `/opt/vocalguard/.env` / `.env.prod` | `QDRANT_URL` | `http://node15.lan:6333` |

Sans `QDRANT_URL`, le predict ne tente pas localhost (evite une latence inutile).

## Code (fichiers cles)

| Fichier | Role |
|---------|------|
| `backend/voice/qdrant_intents.py` | Client HTTP : ensure collection, upsert, delete, `fetch_qdrant_status` |
| `backend/services/intent_repository.py` | Predict Qdrant-first ; sync upsert/delete ; `predict_intent_scores_detailed` |
| `backend/api/routes/kb.py` | `conversation-status` qdrant_* ; chat/predict renvoient `source` |
| `backend/stt_service/app.py` | Health `qdrant_ok` |
| `scripts/migrate_intents_to_qdrant.py` | Migration batch Postgres -> Qdrant |
| `scripts/install_qdrant_node15.sh` | Install binaire + systemd |
| `frontend/src/components/kb/KbVectorEngineChip.tsx` | Chip statut UI |
| `backend/tests/test_qdrant_intents.py` | Tests unitaires mock HTTP |

Embeddings : `backend/voice/intent_embed.py` (hashing n-grams, **dim 384**, L2-normalise).

Payload Qdrant par point :

```json
{
  "intent_tag": "prise_rdv",
  "ref_type": "pattern",
  "ref_id": 123
}
```

ID point = `intent_embeddings.id`. Poids : `pattern` = 1.0, `response` = 0.35.

## Migration des intents

```bash
export DATABASE_URL="postgresql+psycopg2://USER:PASS@node14.lan:5432/vocalguard"
export QDRANT_URL="http://127.0.0.1:6333"
cd /opt/vocalguard-stt
PYTHONPATH=. ./venv/bin/python scripts/migrate_intents_to_qdrant.py
```

Idempotent (memes IDs). Apres seed / edit KB, les upserts runtime via `QDRANT_URL`
maintiennent Qdrant ; sinon relancer la migration.

## Validations (2026-09-14)

- Recherche Qdrant seule : ~11 ms, top `prise_rdv`
- `/v1/intent-predict` STT : OK (~50-150 ms avec boost Postgres)
- Collection `points_count` ~596, status green
- Bench API node14 historique ~5.6 s quand le chat proxyait node15 en 30 s ;
  depuis, le tchat UI predit en local (Qdrant) et expose `source: qdrant`

## UI

- Page `/kb` : chip `KbVectorEngineChip` (Qdrant · N pts)
- `GET /api/v1/kb/conversation-status` : `qdrant_ok`, `qdrant_points`, `vector_engine`
- Modale tchatche (existante sur `/kb`) : bulles peuvent afficher `engine` / `source`
- Settings conversation : bandeau readiness (STT + intents + mention Qdrant)

## Tests locaux

```bash
pytest backend/tests/test_qdrant_intents.py -q
pytest backend/tests/test_intent_vector_predict.py -q
```

## Pistes ouvertes

- Profiling boost lexical Postgres (encore potentiellement lent)
- Index payload Qdrant (filtres `enabled`)
- Suppression eventuelle de la colonne pgvector une fois Qdrant stable

## Liens

- Vue voix : [VOICE_NODE15.md](VOICE_NODE15.md)
- Postgres : [POSTGRES.md](POSTGRES.md)
- Seed IVR : `config/README_INTENTS_IVR.md`
