# Voice conversation / KB (node15 + intents Postgres)

## Architecture

- **node14** : telephonie, VAD tour (`TurnVad`), belief intents, play WAV modem sous `ivr_wav/kb_*.wav`.
- **node15** : `POST /v1/transcribe?mode=live|final`, `POST /v1/intent-predict`, `POST /v1/tts`, `POST /v1/greeting-mix` (TTS + mix intro).
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
