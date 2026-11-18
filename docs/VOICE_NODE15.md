# Voice conversation / KB (node15 + intents Postgres)

## Architecture

- **node14** : telephonie, VAD tour (`TurnVad`), belief intents, play WAV modem sous `ivr_wav/kb_*.wav`.
- **node15** : `POST /v1/transcribe?mode=live|final`, `POST /v1/intent-predict`, `POST /v1/tts`, `POST /v1/greeting-mix` (TTS + mix intro, legacy).
- **Accueil entrant prod** : ElevenLabs sur **node14** (`tts_provider: elevenlabs`), pas Edge ni `greeting-mix` node15 (voir [INSTALLATION_LAN.md](INSTALLATION_LAN.md) section 2.6).
- **Postgres** : tables `intents`, `intent_patterns`, `intent_responses`, `intent_embeddings` (+ colonne `embedding` pgvector), `call_leads`.
- Seed one-shot : `data/intents/kb_seed/conversation_v1.json` (plus de JSON runtime).

## Activer le mode conversation

Priorite (du plus fort au plus faible) :

1. Settings UI : **Messagerie et DTMF** → Mode = `Conversation`
2. Variable d'env : `VOICEMAIL_MODE=conversation`
3. YAML : `voicemail_mode: conversation`

Aussi :

```text
STT_SERVICE_URL=http://node15.lan:8100
TTS_SERVICE_URL=http://node15.lan:8100
```

`TTS_SERVICE_URL` pilote la synthese distante (conversation, prefetch KB, anciens apercus Edge).
Si omis, repli sur `STT_SERVICE_URL` (meme daemon). **Ne pas** s'en servir pour l'accueil modem en prod : preferer ElevenLabs (mix local node14).

`POST /v1/greeting-mix` (node15) reste pour les configs `tts_provider: edge` / legacy uniquement.

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

Utilise `TTS_SERVICE_URL` (ou ElevenLabs si configure sur l'accueil) selon les intents KB.
L'accueil modem regenere reste ElevenLabs + mix sur node14.

## Bench latence

```text
python scripts/bench_node15_voice_latency.py --url http://node15.lan:8100
```

Si node15 absent : exit 0 (SKIP). Gate indicative : STT live p95 < 2.5 s.
