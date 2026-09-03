"""
Client HTTP vers le service STT distant (vocalguard-stt).
"""

from __future__ import annotations

import io
from typing import Any, Optional

import httpx
from loguru import logger


async def transcribe_pcm_remote(
    base_url: str,
    audio_pcm: bytes,
    *,
    sample_rate: int = 16000,
    token: Optional[str] = None,
    timeout_sec: float = 600.0,
) -> str:
    """
    Envoie du PCM 16 kHz au service STT via un WAV temporaire en memoire.

    @param base_url URL de base (ex. http://node15.lan:8100).
    @param audio_pcm PCM 16-bit mono little-endian.
    @param sample_rate Taux d'echantillonnage source.
    @param token Token X-STT-Token optionnel.
    @param timeout_sec Delai max requete (Whisper CPU lent: ~600s).
    @returns Texte transcrit.
    @raises httpx.HTTPError Si le service est injoignable ou renvoie une erreur.
    """
    result = await transcribe_pcm_remote_detailed(
        base_url,
        audio_pcm,
        sample_rate=sample_rate,
        token=token,
        timeout_sec=timeout_sec,
    )
    return result.get("text") or ""


async def transcribe_pcm_remote_detailed(
    base_url: str,
    audio_pcm: bytes,
    *,
    sample_rate: int = 16000,
    token: Optional[str] = None,
    timeout_sec: float = 600.0,
) -> dict[str, Any]:
    """
    Transcription distante avec cues SRT si le service les renvoie.

    @returns Dict text, cues.
    """
    if not audio_pcm:
        return {"text": "", "cues": []}
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_pcm)
    buf.seek(0)

    headers: dict[str, str] = {}
    if token:
        headers["X-STT-Token"] = token

    url = f"{base_url.rstrip('/')}/v1/transcribe"
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        files = {"file": ("audio.wav", buf.read(), "audio/wav")}
        response = await client.post(url, files=files, headers=headers)
        response.raise_for_status()
        payload = response.json()
    text = (payload.get("text") or "").strip()
    cues = payload.get("cues") if isinstance(payload.get("cues"), list) else []
    logger.debug("STT distant OK ({} octets -> {} chars, {} cues)", len(audio_pcm), len(text), len(cues))
    return {"text": text, "cues": cues}


async def check_stt_service_health(base_url: str, timeout_sec: float = 3.0) -> bool:
    """
    Verifie que le service STT repond et a charge le modele.

    @param base_url URL de base du service.
    @returns True si /health indique model_loaded.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(f"{base_url.rstrip('/')}/health")
            if r.status_code != 200:
                return False
            body = r.json()
            return bool(body.get("model_loaded"))
    except Exception as exc:
        logger.debug("STT distant health KO: {}", exc)
        return False
