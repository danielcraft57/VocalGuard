"""
Client TTS ElevenLabs (HTTP) avec garde-fous quota / rate limit.

Utilise uniquement si ``ELEVENLABS_API_KEY`` (ou config) est defini.
Prefetch offline recommande - eviter les appels live pendant un appel.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from loguru import logger

DEFAULT_API_BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"

# Pause entre requetes (secondes) pour limiter le debit.
DEFAULT_THROTTLE_SEC = 0.35
# Texte max pour un apercu (economise le quota).
PREVIEW_MAX_CHARS = 80


class ElevenLabsQuotaError(RuntimeError):
    """Quota ou rate-limit ElevenLabs (429 / 401)."""


class ElevenLabsTts:
    """
    Synthese ElevenLabs avec cache fichier et throttle.

    @param api_key Cle API (xi-api-key).
    @param voice_id Identifiant voix.
    @param model_id Modele TTS.
    @param cache_dir Dossier cache MP3/bytes.
    @param throttle_sec Pause minimale entre appels API.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str = DEFAULT_VOICE_ID,
        model_id: str = DEFAULT_MODEL_ID,
        cache_dir: Optional[Path] = None,
        throttle_sec: float = DEFAULT_THROTTLE_SEC,
        api_base: str = DEFAULT_API_BASE,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.voice_id = (voice_id or DEFAULT_VOICE_ID).strip()
        self.model_id = (model_id or DEFAULT_MODEL_ID).strip()
        self.api_base = (api_base or DEFAULT_API_BASE).rstrip("/")
        self.throttle_sec = max(0.0, float(throttle_sec))
        self.cache_dir = Path(cache_dir) if cache_dir else Path("audio_cache") / "elevenlabs"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_call_monotonic = 0.0
        self.chars_consumed = 0
        self.requests_ok = 0
        self.requests_failed = 0
        self.stopped_reason: Optional[str] = None

    @classmethod
    def from_config(cls, config: Any) -> Optional["ElevenLabsTts"]:
        """
        Construit un client depuis Config app si cle presente.

        @param config Objet Config VocalGuard.
        @returns Instance ou None.
        """
        key = (
            getattr(config, "elevenlabs_api_key", None)
            or os.getenv("ELEVENLABS_API_KEY", "")
        )
        key = (key or "").strip()
        if not key:
            return None
        voice = (
            getattr(config, "elevenlabs_voice_id", None)
            or os.getenv("ELEVENLABS_VOICE_ID", "")
            or DEFAULT_VOICE_ID
        )
        model = (
            getattr(config, "elevenlabs_model_id", None)
            or os.getenv("ELEVENLABS_MODEL_ID", "")
            or DEFAULT_MODEL_ID
        )
        base = Path(getattr(config, "base_path", None) or ".")
        return cls(
            api_key=key,
            voice_id=str(voice).strip(),
            model_id=str(model).strip(),
            cache_dir=base / "audio_cache" / "elevenlabs",
        )

    def cache_key(self, text: str) -> str:
        """
        Hash stable texte + voix + modele.

        @param text Texte a synthetiser.
        @returns Hex court.
        """
        raw = f"{self.voice_id}|{self.model_id}|{(text or '').strip()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def cached_path(self, text: str) -> Path:
        """
        Chemin cache MP3 pour un texte.

        @param text Phrase.
        @returns Path ``.mp3``.
        """
        return self.cache_dir / f"{self.cache_key(text)}.mp3"

    async def _throttle(self) -> None:
        """Attend si besoin entre deux appels API."""
        if self.throttle_sec <= 0:
            return
        now = time.monotonic()
        wait = self.throttle_sec - (now - self._last_call_monotonic)
        if wait > 0:
            await asyncio.sleep(wait)

    async def synthesize(
        self,
        text: str,
        *,
        force: bool = False,
        preview: bool = False,
    ) -> bytes:
        """
        Synthetise un texte en audio MPEG (mp3).

        Utilise le cache disque sauf ``force``. Sur 429/401 leve
        ``ElevenLabsQuotaError`` et pose ``stopped_reason``.

        @param text Phrase a dire.
        @param force Ignore le cache.
        @param preview Tronque le texte (quota).
        @returns Octets MP3.
        @raises ElevenLabsQuotaError Si quota / auth.
        @raises RuntimeError Si HTTP autre erreur.
        """
        if self.stopped_reason:
            raise ElevenLabsQuotaError(self.stopped_reason)

        speak = (text or "").strip()
        if not speak:
            raise ValueError("Texte ElevenLabs vide")
        if preview and len(speak) > PREVIEW_MAX_CHARS:
            speak = speak[: PREVIEW_MAX_CHARS - 1].rstrip() + "."

        path = self.cached_path(speak)
        if not force and path.is_file() and path.stat().st_size > 100:
            return path.read_bytes()

        await self._throttle()
        url = f"{self.api_base}/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "text": speak,
            "model_id": self.model_id,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                self._last_call_monotonic = time.monotonic()
                resp = await client.post(url, headers=headers, json=body)
                if resp.status_code in (401, 403):
                    self.stopped_reason = f"ElevenLabs auth HTTP {resp.status_code}"
                    self.requests_failed += 1
                    raise ElevenLabsQuotaError(self.stopped_reason)
                if resp.status_code == 429:
                    self.stopped_reason = "ElevenLabs rate limit / quota (429)"
                    self.requests_failed += 1
                    raise ElevenLabsQuotaError(self.stopped_reason)
                if resp.status_code >= 400:
                    self.requests_failed += 1
                    raise RuntimeError(
                        f"ElevenLabs HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                audio = resp.content
        except ElevenLabsQuotaError:
            raise
        except Exception as exc:
            self.requests_failed += 1
            logger.warning("ElevenLabs synthesize echoue: {}", exc)
            raise

        path.write_bytes(audio)
        self.chars_consumed += len(speak)
        self.requests_ok += 1
        logger.debug(
            "ElevenLabs OK chars={} total_chars={} cache={}",
            len(speak),
            self.chars_consumed,
            path.name,
        )
        return audio

    def stats(self) -> Dict[str, Any]:
        """
        Compteurs pour logs / UI prefetch.

        @returns Dict ok/failed/chars/stopped_reason.
        """
        return {
            "requests_ok": self.requests_ok,
            "requests_failed": self.requests_failed,
            "chars_consumed": self.chars_consumed,
            "stopped_reason": self.stopped_reason,
            "voice_id": self.voice_id,
            "model_id": self.model_id,
        }
