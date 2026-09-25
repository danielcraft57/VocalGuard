# Qdrant intents (node15) - journal d'integration

Document de reference pour la BDD vectorielle des intents VocalGuard.
Installee **sans Docker** sur `pi@node15.lan`, integree au predict KB / STT / UI.

Cutover LAN : 2026-09-14. UI statut + display moteur : 2026-09-15 (restaure en repo 2026-09-24).
Collections duales (inbound + outbound commercial) : 2026-09-25.

## Objectif

Accelerer la recherche d'intents (ANN cosine) en sortant le chemin chaud
de Postgres/pgvector (node14) vers Qdrant local sur node15, au plus pres
du service voix (`vocalguard-stt` :8100).

Postgres reste la source de verite metier (tags, patterns, responses, CRUD).
Qdrant stocke les vecteurs + payload leger pour la recherche.

## Collections

| Role | Collection | Profil Postgres |
|------|------------|-----------------|
| Appels entrants (KB conversation) | `intents_inbound` | `inbound` |
| Appel commercial sortant | `intents_outbound_commercial` | `outbound_commercial` |

Ancien nom unique `intents` : migrer avec
`python scripts/migrate_intents_to_qdrant.py --profile inbound --rename-legacy`.

## Architecture

```text
                    +------------------+
  UI / API node14   | Postgres node14  |  intents (+ profile), patterns,
  CRUD KB --------->| + pgvector       |  responses, embedding_json
                    +--------+---------+
                             | migrate / sync upsert
                             v
  node15 STT :8100  +------------------+
  intent-predict -->| Qdrant :6333     |  intents_inbound
  (QDRANT_URL)      | dim 384 Cosine   |  intents_outbound_commercial
                    +------------------+
```

Ordre de predict (`backend/services/intent_repository.py`) :

1. **Qdrant** si `QDRANT_URL` est defini (collection selon `profile`)
2. sinon **pgvector** SQL (filtre profile)
3. sinon **cosine Python**

Puis boost lexical Postgres (filtre profile).

## Migration

```bash
export DATABASE_URL="postgresql+psycopg2://USER:PASS@node14.lan:5432/vocalguard"
export QDRANT_URL="http://127.0.0.1:6333"
PYTHONPATH=. python scripts/migrate_intents_to_qdrant.py --profile all
PYTHONPATH=. python scripts/migrate_intents_to_qdrant.py --profile inbound --rename-legacy
```

## Appel commercial sortant

1. `POST /api/v1/kb/outbound-commercial/seed`
2. `POST /api/v1/kb/outbound-commercial/voices/regenerate` (`tts_provider`: edge|elevenlabs)
3. Dialer : cocher "Appel commercial"
4. STT -> `outbound.commercial.suggestions` (top-5)
5. Touches 1-5 : situation puis phrase -> play `out_kb_*.wav`

ElevenLabs : cle `ELEVENLABS_API_KEY` en `.env` uniquement. Prefetch offline + cache + stop sur 429.

## Fichiers cles

- `backend/voice/qdrant_intents.py`
- `backend/services/intent_repository.py`
- `backend/services/outbound_commercial_engine.py`
- `backend/api/routes/outbound_commercial.py`
- `backend/voice/elevenlabs_tts.py`
- `data/intents/kb_seed/outbound_commercial_v1.json`
- `scripts/migrate_intents_to_qdrant.py`

## Liens

- [VOICE_NODE15.md](VOICE_NODE15.md)
- [POSTGRES.md](POSTGRES.md)
