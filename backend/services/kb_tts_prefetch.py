"""
Prefetch TTS intents : node15 (ou local) → conversion modem → ivr_wav/kb_*.wav.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

from backend.services import intent_repository as intent_repo
from backend.voice.audio_utils import tts_source_to_modem_wav
from backend.voice.ivr_cache import IvrAudioCache, ivr_content_hash
from backend.voice.modem_profile import resolve_profile_from_config
from backend.voice.node15_voice_client import Node15VoiceClient
from backend.voice.response_picker import variant_wav_basename
from backend.voice.tts_url import resolve_tts_service_url, resolve_tts_token

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.core.config import Config
    from backend.voice.synthesis import VoiceSynthesis


async def prefetch_intent_voices(
    db: "Session",
    config: "Config",
    synthesis: "VoiceSynthesis",
    *,
    force: bool = False,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Regenerere les WAV modem pour chaque variante de reponse d'intent.

    Utilise node15 /v1/tts si ``TTS_SERVICE_URL`` (ou ``STT_SERVICE_URL``) est defini,
    sinon TTS local.

    @param db Session Postgres.
    @param config Config app (voix greeting).
    @param synthesis Moteur local de secours.
    @param force Ignore le cache hash.
    @param tags Sous-ensemble de tags (None = tous enabled).
    @returns Stats {ok, skipped, failed, details}.
    """
    cache = IvrAudioCache(config, synthesis)
    intents = intent_repo.list_intents_detailed(db, enabled_only=True)
    if tags:
        wanted = {t.strip() for t in tags if t and t.strip()}
        intents = [i for i in intents if i["tag"] in wanted]

    voice = getattr(config, "edge_tts_voice", None) or "fr-FR-DeniseNeural"
    rate = getattr(config, "edge_tts_rate", None) or "+0%"
    pitch = getattr(config, "edge_tts_pitch", None) or "+0Hz"
    client: Optional[Node15VoiceClient] = None
    tts_url = resolve_tts_service_url(config)
    if tts_url:
        client = Node15VoiceClient(
            tts_url,
            token=resolve_tts_token(config),
            timeout_sec=180.0,
        )

    ok = 0
    skipped = 0
    failed = 0
    details: List[Dict[str, Any]] = []
    profile = resolve_profile_from_config(config)

    for intent in intents:
        tag = str(intent["tag"])
        responses = [str(r).strip() for r in (intent.get("responses") or []) if str(r).strip()]
        if not responses:
            failed += 1
            details.append({"tag": tag, "status": "failed", "reason": "pas de response"})
            continue

        for idx, text in enumerate(responses):
            basename = variant_wav_basename(tag, idx)
            # Respecte wav_basename custom pour la variante 0
            custom = intent.get("wav_basename")
            if idx == 0 and custom:
                basename = str(custom)

            if not force and cache.is_fresh(basename, text):
                skipped += 1
                details.append(
                    {"tag": tag, "status": "skipped", "basename": basename, "variant": idx}
                )
                continue

            try:
                if client is not None:
                    audio_bytes = await client.tts(text, voice=voice, rate=rate, pitch=pitch)
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                        src = Path(tmp.name)
                        src.write_bytes(audio_bytes)
                    try:
                        out = cache.cache_dir / f"{basename}.wav"
                        tts_source_to_modem_wav(src, out, profile=profile)
                        h = ivr_content_hash(
                            text,
                            "edge",
                            voice,
                            rate,
                            pitch,
                            float(getattr(config, "edge_tts_voice_gain_db", -6.0) or -6.0),
                            profile_sample_rate=profile.sample_rate,
                            profile_sample_width=profile.sample_width,
                        )
                        meta = cache.cache_dir / f"{basename}.meta.json"
                        meta.write_text(
                            json.dumps(
                                {
                                    "hash": h,
                                    "text": text,
                                    "tag": tag,
                                    "variant": idx,
                                    "engine": "edge-node15",
                                },
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
                    finally:
                        try:
                            src.unlink(missing_ok=True)
                        except OSError:
                            pass
                else:
                    path = await cache.ensure(text, basename)
                    if path is None:
                        raise RuntimeError("ensure TTS local a echoue")
                ok += 1
                details.append(
                    {"tag": tag, "status": "ok", "basename": basename, "variant": idx}
                )
            except Exception as exc:
                failed += 1
                logger.exception("Prefetch voix intent {}#{}: {}", tag, idx, exc)
                details.append(
                    {
                        "tag": tag,
                        "status": "failed",
                        "variant": idx,
                        "reason": str(exc),
                    }
                )

    return {"ok": ok, "skipped": skipped, "failed": failed, "details": details}
