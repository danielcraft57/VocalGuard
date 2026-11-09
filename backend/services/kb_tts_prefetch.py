"""
Prefetch TTS intents : Edge (node15/local) ou ElevenLabs → ivr_wav/*.wav.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

from backend.services import intent_repository as intent_repo
from backend.voice.audio_utils import tts_source_to_modem_wav
from backend.voice.elevenlabs_tts import ElevenLabsQuotaError, ElevenLabsTts
from backend.voice.ivr_cache import IvrAudioCache, ivr_content_hash
from backend.voice.modem_profile import resolve_profile_from_config
from backend.voice.node15_voice_client import Node15VoiceClient
from backend.voice.qdrant_intents import PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL
from backend.voice.response_picker import variant_wav_basename
from backend.voice.elevenlabs_client import ELEVENLABS_VOICE_MATILDA
from backend.voice.tts_url import resolve_tts_service_url, resolve_tts_token

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from backend.core.config import Config
    from backend.voice.synthesis import VoiceSynthesis


async def _write_modem_wav_from_mp3(
    *,
    audio_bytes: bytes,
    basename: str,
    cache: IvrAudioCache,
    modem_profile: Any,
    meta: Dict[str, Any],
) -> None:
    """
    Ecrit un MP3 temporaire converti en WAV modem + meta JSON.

    @param audio_bytes Contenu MP3.
    @param basename Sans extension.
    @param cache Cache IVR.
    @param modem_profile Profil modem.
    @param meta Dict meta a ecrire.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        src = Path(tmp.name)
        src.write_bytes(audio_bytes)
    try:
        out = cache.cache_dir / f"{basename}.wav"
        tts_source_to_modem_wav(src, out, profile=modem_profile)
        meta_path = cache.cache_dir / f"{basename}.meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False),
            encoding="utf-8",
        )
    finally:
        try:
            src.unlink(missing_ok=True)
        except OSError:
            pass


async def prefetch_intent_voices(
    db: "Session",
    config: "Config",
    synthesis: "VoiceSynthesis",
    *,
    force: bool = False,
    tags: Optional[List[str]] = None,
    profile: Optional[str] = None,
    tts_provider: Optional[str] = None,
    edge_tts_voice: Optional[str] = None,
    edge_tts_rate: Optional[str] = None,
    edge_tts_pitch: Optional[str] = None,
    tts_voice_gain_db: Optional[float] = None,
    elevenlabs_voice_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Regenerere les WAV modem pour chaque variante de reponse d'intent.

    @param db Session Postgres.
    @param config Config app.
    @param synthesis Moteur local de secours.
    @param force Ignore le cache hash.
    @param tags Sous-ensemble de tags.
    @param profile Filtre catalogue.
    @param tts_provider ``edge`` | ``elevenlabs``.
    @param edge_tts_voice Override voix Edge.
    @param edge_tts_rate Override debit.
    @param edge_tts_pitch Override hauteur.
    @param tts_voice_gain_db Override volume (dB).
    @param elevenlabs_voice_id Override voix ElevenLabs.
    @returns Stats ok/skipped/failed/details/provider.
    """
    cache = IvrAudioCache(config, synthesis)
    intents = intent_repo.list_intents_detailed(
        db, enabled_only=True, profile=profile
    )
    if tags:
        wanted = {t.strip() for t in tags if t and t.strip()}
        intents = [i for i in intents if i["tag"] in wanted]

    if profile == PROFILE_OUTBOUND_COMMERCIAL:
        if tts_provider is None and not getattr(config, "tts_provider", None):
            tts_provider = "elevenlabs"
        _vid = (elevenlabs_voice_id or "").strip()
        if not _vid or _vid == "JBFqnCBsd6RMkjVDRZzb":
            elevenlabs_voice_id = ELEVENLABS_VOICE_MATILDA
        if not (edge_tts_voice or "").strip():
            edge_tts_voice = "fr-FR-DeniseNeural"

    provider = (
        (tts_provider or getattr(config, "tts_provider", None) or "edge")
        .strip()
        .lower()
    )
    if provider not in ("edge", "elevenlabs"):
        provider = "edge"

    if profile == PROFILE_OUTBOUND_COMMERCIAL and provider == "edge":
        if not (edge_tts_voice or "").strip():
            edge_tts_voice = "fr-FR-DeniseNeural"
        elif "Henri" in edge_tts_voice or "henri" in edge_tts_voice.lower():
            edge_tts_voice = "fr-FR-DeniseNeural"

    eleven: Optional[ElevenLabsTts] = None
    if provider == "elevenlabs":
        eleven = ElevenLabsTts.from_config(config)
        voice_id = (elevenlabs_voice_id or "").strip()
        if profile == PROFILE_OUTBOUND_COMMERCIAL and (
            not voice_id or voice_id == "JBFqnCBsd6RMkjVDRZzb"
        ):
            voice_id = ELEVENLABS_VOICE_MATILDA
        if voice_id and eleven is not None:
            eleven.voice_id = voice_id
        if eleven is None:
            logger.warning(
                "Prefetch ElevenLabs demande mais cle absente - fallback Edge"
            )
            provider = "edge"

    voice = (
        (edge_tts_voice or getattr(config, "edge_tts_voice", None) or "fr-FR-DeniseNeural")
        .strip()
    )
    rate = (edge_tts_rate or getattr(config, "edge_tts_rate", None) or "+0%").strip()
    pitch = (edge_tts_pitch or getattr(config, "edge_tts_pitch", None) or "+0Hz").strip()
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
    modem_profile = resolve_profile_from_config(config)
    used_provider = provider
    if tts_voice_gain_db is not None:
        gain = float(tts_voice_gain_db)
    else:
        gain = float(getattr(config, "edge_tts_voice_gain_db", -6.0) or -6.0)

    async def _synth_edge(text: str, basename: str, tag: str, idx: int) -> str:
        """Synthese Edge → WAV. Retourne label engine."""
        if client is not None:
            audio_bytes = await client.tts(text, voice=voice, rate=rate, pitch=pitch)
            h = ivr_content_hash(
                text,
                "edge",
                voice,
                rate,
                pitch,
                gain,
                profile_sample_rate=modem_profile.sample_rate,
                profile_sample_width=modem_profile.sample_width,
            )
            await _write_modem_wav_from_mp3(
                audio_bytes=audio_bytes,
                basename=basename,
                cache=cache,
                modem_profile=modem_profile,
                meta={
                    "hash": h,
                    "text": text,
                    "tag": tag,
                    "variant": idx,
                    "engine": "edge-node15",
                },
            )
            return "edge-node15"
        path = await cache.ensure(text, basename)
        if path is None:
            raise RuntimeError("ensure TTS local a echoue")
        return "edge-local"

    for intent in intents:
        tag = str(intent["tag"])
        custom_base = intent.get("wav_basename")
        responses = [
            str(r).strip() for r in (intent.get("responses") or []) if str(r).strip()
        ]
        if not responses:
            failed += 1
            details.append({"tag": tag, "status": "failed", "reason": "pas de response"})
            continue

        for idx, text in enumerate(responses):
            basename = variant_wav_basename(
                tag,
                idx,
                wav_basename=str(custom_base) if custom_base else None,
            )
            if not force and cache.is_fresh(basename, text):
                skipped += 1
                details.append(
                    {
                        "tag": tag,
                        "status": "skipped",
                        "basename": basename,
                        "variant": idx,
                    }
                )
                continue

            try:
                engine_label = "edge"
                if provider == "elevenlabs" and eleven is not None:
                    try:
                        audio_bytes = await eleven.synthesize(text, force=force)
                        h = ivr_content_hash(
                            text,
                            "elevenlabs",
                            eleven.voice_id,
                            eleven.model_id,
                            "",
                            gain,
                            profile_sample_rate=modem_profile.sample_rate,
                            profile_sample_width=modem_profile.sample_width,
                        )
                        await _write_modem_wav_from_mp3(
                            audio_bytes=audio_bytes,
                            basename=basename,
                            cache=cache,
                            modem_profile=modem_profile,
                            meta={
                                "hash": h,
                                "text": text,
                                "tag": tag,
                                "variant": idx,
                                "engine": "elevenlabs",
                                "voice_id": eleven.voice_id,
                            },
                        )
                        engine_label = "elevenlabs"
                    except ElevenLabsQuotaError as quota_exc:
                        logger.warning(
                            "ElevenLabs quota - fallback Edge {}#{}: {}",
                            tag,
                            idx,
                            quota_exc,
                        )
                        provider = "edge"
                        used_provider = "edge_fallback"
                        eleven = None
                        engine_label = await _synth_edge(text, basename, tag, idx)
                else:
                    engine_label = await _synth_edge(text, basename, tag, idx)

                ok += 1
                details.append(
                    {
                        "tag": tag,
                        "status": "ok",
                        "basename": basename,
                        "variant": idx,
                        "engine": engine_label,
                    }
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

    result: Dict[str, Any] = {
        "ok": ok,
        "skipped": skipped,
        "failed": failed,
        "details": details,
        "provider": used_provider,
        "profile": profile or PROFILE_INBOUND,
    }
    if eleven is not None:
        result["elevenlabs"] = eleven.stats()
    return result


async def preview_tts_audio(
    config: "Config",
    text: str,
    *,
    tts_provider: Optional[str] = None,
    edge_tts_voice: Optional[str] = None,
    edge_tts_rate: Optional[str] = None,
    edge_tts_pitch: Optional[str] = None,
    elevenlabs_voice_id: Optional[str] = None,
) -> tuple[bytes, str]:
    """
    Synthetise un apercu audio (sans ecrire le catalogue ivr_wav).

    @param config Config app.
    @param text Phrase a dire.
    @param tts_provider edge | elevenlabs.
    @param edge_tts_voice Voix Edge.
    @param edge_tts_rate Debit.
    @param edge_tts_pitch Hauteur.
    @param elevenlabs_voice_id Voix ElevenLabs.
    @returns (bytes audio, media_type).
    @raises RuntimeError Si synthese impossible.
    """
    phrase = (text or "").strip()
    if not phrase:
        raise RuntimeError("Texte vide")

    provider = (
        (tts_provider or getattr(config, "tts_provider", None) or "edge")
        .strip()
        .lower()
    )
    if provider not in ("edge", "elevenlabs"):
        provider = "edge"

    if provider == "elevenlabs":
        eleven = ElevenLabsTts.from_config(config)
        if eleven is not None and elevenlabs_voice_id:
            eleven.voice_id = str(elevenlabs_voice_id).strip()
        if eleven is not None:
            audio = await eleven.synthesize(phrase, force=True)
            return audio, "audio/mpeg"
        logger.warning("Preview ElevenLabs indisponible - fallback Edge")
        provider = "edge"

    voice = (
        (edge_tts_voice or getattr(config, "edge_tts_voice", None) or "fr-FR-DeniseNeural")
        .strip()
    )
    rate = (edge_tts_rate or getattr(config, "edge_tts_rate", None) or "+0%").strip()
    pitch = (edge_tts_pitch or getattr(config, "edge_tts_pitch", None) or "+0Hz").strip()

    tts_url = resolve_tts_service_url(config)
    if tts_url:
        client = Node15VoiceClient(
            tts_url,
            token=resolve_tts_token(config),
            timeout_sec=60.0,
        )
        audio = await client.tts(phrase, voice=voice, rate=rate, pitch=pitch)
        return audio, "audio/mpeg"

    raise RuntimeError("Aucun moteur TTS disponible pour l'apercu")
