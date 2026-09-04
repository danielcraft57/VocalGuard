"""
Client HTTP vers le service voix node15 (STT live, intent-predict, TTS).
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger


class Node15VoiceClient:
    """
    Client vers vocalguard-stt etendu (transcribe / intent-predict / tts).

    @param base_url URL ex. http://node15.lan:8100.
    @param token Header X-STT-Token optionnel.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: Optional[str] = None,
        timeout_sec: float = 60.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.token = (token or "").strip() or None
        self.timeout_sec = float(timeout_sec)

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.token:
            headers["X-STT-Token"] = self.token
        return headers

    async def health(self) -> Dict[str, Any]:
        """
        GET /health.

        @returns Corps JSON ou dict status error.
        """
        if not self.base_url:
            return {"status": "error", "detail": "base_url vide"}
        try:
            async with httpx.AsyncClient(timeout=min(5.0, self.timeout_sec)) as client:
                r = await client.get(f"{self.base_url}/health")
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def transcribe(
        self,
        audio_pcm: bytes,
        *,
        sample_rate: int = 16000,
        mode: str = "live",
    ) -> Dict[str, Any]:
        """
        POST /v1/transcribe (multipart) avec query mode=live|final.

        @param audio_pcm PCM s16le mono.
        @param sample_rate Taux.
        @param mode live (rapide) ou final.
        @returns Dict text, cues, engine.
        @raises httpx.HTTPError Sur echec reseau / HTTP.
        """
        if not audio_pcm:
            return {"text": "", "cues": [], "engine": ""}
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_pcm)
        buf.seek(0)
        url = f"{self.base_url}/v1/transcribe"
        params = {"mode": mode}
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            files = {"file": ("audio.wav", buf.read(), "audio/wav")}
            response = await client.post(
                url, files=files, headers=self._headers(), params=params
            )
            response.raise_for_status()
            payload = response.json()
        return {
            "text": (payload.get("text") or "").strip(),
            "cues": payload.get("cues") if isinstance(payload.get("cues"), list) else [],
            "engine": payload.get("engine") or "",
        }

    async def intent_predict(self, text: str, *, top_k: int = 8) -> List[Dict[str, Any]]:
        """
        POST /v1/intent-predict.

        @param text Texte cumule.
        @param top_k Nombre de predictions.
        @returns Liste {tag, score}.
        """
        url = f"{self.base_url}/v1/intent-predict"
        body = {"text": text, "top_k": int(top_k)}
        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            response = await client.post(url, json=body, headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        preds = payload.get("top_predictions") or payload.get("predictions") or []
        if not isinstance(preds, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in preds:
            if not isinstance(item, dict):
                continue
            tag = item.get("tag")
            if not tag:
                continue
            out.append({"tag": str(tag), "score": float(item.get("score") or 0.0)})
        return out

    async def tts(
        self,
        text: str,
        *,
        voice: str = "fr-FR-DeniseNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        """
        POST /v1/tts — retourne bytes audio (wav/mp3 selon service).

        @param text Texte a synthetiser.
        @param voice Voix edge-tts.
        @param rate Vitesse.
        @param pitch Hauteur.
        @returns Contenu fichier audio.
        """
        url = f"{self.base_url}/v1/tts"
        body = {
            "text": text,
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
        }
        async with httpx.AsyncClient(timeout=max(self.timeout_sec, 120.0)) as client:
            response = await client.post(url, json=body, headers=self._headers())
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "application/json" in content_type:
                # Certains deploiements renvoient {audio_b64}
                import base64

                payload = response.json()
                b64 = payload.get("audio_b64") or payload.get("data")
                if not b64:
                    raise RuntimeError("TTS JSON sans audio_b64")
                return base64.b64decode(b64)
            data = response.content
            logger.debug("TTS node15 OK ({} octets)", len(data))
            return data

    async def greeting_mix(
        self,
        text: str,
        *,
        voice: str = "fr-FR-DeniseNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        tts_voice_gain_db: float = -6.0,
        intro_mode: str = "none",
        intro_variant: str = "tesla",
        intro_sec: float = 2.2,
        crossfade_ms: int = 380,
        voice_bed_db: float = -18.0,
        voice_mix_gain_db: float = 0.0,
        track_duck_db: float = 0.0,
        music_offset_sec: float = 0.0,
        bed_variant: Optional[str] = None,
        sample_rate: int = 11025,
        sample_width: int = 2,
        append_beep: bool = True,
        beep_gap_ms: int = 500,
        output: str = "modem",
        intro_path: Optional[Path] = None,
        beep_path: Optional[Path] = None,
    ) -> bytes:
        """
        POST /v1/greeting-mix — TTS + mix intro sur node15.

        @param text Texte accueil.
        @param output modem | listen | voice.
        @param intro_path Fichier intro local a uploader.
        @param beep_path Fichier bip local a uploader.
        @returns Bytes WAV.
        """
        url = f"{self.base_url}/v1/greeting-mix"
        data = {
            "text": text,
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "tts_voice_gain_db": str(tts_voice_gain_db),
            "intro_mode": intro_mode,
            "intro_variant": intro_variant,
            "intro_sec": str(intro_sec),
            "crossfade_ms": str(crossfade_ms),
            "voice_bed_db": str(voice_bed_db),
            "voice_mix_gain_db": str(voice_mix_gain_db),
            "track_duck_db": str(track_duck_db),
            "music_offset_sec": str(music_offset_sec),
            "bed_variant": bed_variant or "",
            "sample_rate": str(sample_rate),
            "sample_width": str(sample_width),
            "append_beep": "1" if append_beep else "0",
            "beep_gap_ms": str(beep_gap_ms),
            "output": output,
        }
        files = []
        handles = []
        try:
            if intro_path and Path(intro_path).is_file():
                handle = open(intro_path, "rb")
                handles.append(handle)
                files.append(
                    (
                        "intro_file",
                        (Path(intro_path).name, handle, "application/octet-stream"),
                    )
                )
            if beep_path and Path(beep_path).is_file():
                handle = open(beep_path, "rb")
                handles.append(handle)
                files.append(
                    (
                        "beep_file",
                        (Path(beep_path).name, handle, "application/octet-stream"),
                    )
                )
            async with httpx.AsyncClient(timeout=max(self.timeout_sec, 180.0)) as client:
                response = await client.post(
                    url,
                    data=data,
                    files=files or None,
                    headers=self._headers(),
                )
                response.raise_for_status()
                payload = response.content
                logger.debug("greeting-mix node15 OK ({} octets)", len(payload))
                return payload
        finally:
            for handle in handles:
                try:
                    handle.close()
                except OSError:
                    pass
