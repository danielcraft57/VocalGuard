# Voice conversation / KB (node15 + intents Postgres / Qdrant)

## Architecture

- **node14** : telephonie, VAD tour (`TurnVad`), belief intents, play WAV modem sous `ivr_wav/kb_*.wav` (entrant) et `out_kb_*.wav` (commercial sortant).
- **node15** : `POST /v1/transcribe?mode=live|final`, `POST /v1/intent-predict`, `POST /v1/tts`, `POST /v1/greeting-mix` (TTS + mix intro).
- **Qdrant** (node15, sans Docker) : collections `intents_inbound` et `intents_outbound_commercial` (vecteurs 384, Cosine). Service systemd `qdrant`, HTTP `:6333`.
- **Postgres** (node14) : tables `intents` (+ `profile`), `intent_patterns`, `intent_responses`, `intent_embeddings` (+ colonne `embedding` pgvector en fallback), `call_leads`.
- Seed inbound : `data/intents/kb_seed/conversation_v1.json`.
- Seed outbound commercial : `data/intents/kb_seed/outbound_commercial_v1.json`.

Predict : Qdrant si `QDRANT_URL` est defini (collection selon `profile`), sinon pgvector, sinon cosine Python.
Migration : `python scripts/migrate_intents_to_qdrant.py --profile all` (voir `scripts/install_qdrant_node15.sh`).
Rename legacy : `--rename-legacy` supprime l'ancienne collection `intents`.

Detail complet (install, env, sync CRUD, benches, journal cutover) :
[QDRANT_INTENTS.md](QDRANT_INTENTS.md).

## Activer le mode conversation

Priorite (du plus fort au plus faible) :

1. Settings UI : **Messagerie et DTMF** → Mode = `Conversation`
2. Variable d'env : `VOICEMAIL_MODE=conversation`
3. YAML : `voicemail_mode: conversation`

Aussi :

```text
STT_SERVICE_URL=http://node15.lan:8100
TTS_SERVICE_URL=http://node15.lan:8100
QDRANT_URL=http://node15.lan:6333
```

`TTS_SERVICE_URL` pilote la synthese distante (accueil incoming-audio, mix, prefetch KB).
Si omis, repli sur `STT_SERVICE_URL` (meme daemon).

L'apercu / regeneration incoming-audio appelle `POST /v1/greeting-mix` : TTS + mix jingle/piste
(+ bip) sur node15, avec upload de l'intro locale. Repli mix local si node15 KO.

Si conversation est demande mais STT indisponible, repli automatique sur le repondeur simple (log `repondeur_conversation_fallback_simple`).

## Migrations

```text
alembic upgrade head
```

Revisions : `003_intents_normalized`, `004_pgvector_intent_embeddings` (extension `vector` sur Postgres).

## Prefetch voix

UI `/kb` → "Regenerer les voix", ou :

```text
POST /api/v1/kb/voices/regenerate
{"force": true}
```

Utilise les params voix d'accueil (`edge_tts_*` / settings incoming-audio)
et `TTS_SERVICE_URL` (repli `STT_SERVICE_URL`) pour la synthese distante.
L'apercu / regeneration incoming-audio passe aussi par ce TTS puis mixe sur node14.

## Bench latence

```text
python scripts/bench_node15_voice_latency.py --url http://node15.lan:8100
```

Si node15 absent : exit 0 (SKIP). Gate indicative : STT live p95 < 2.5 s.
