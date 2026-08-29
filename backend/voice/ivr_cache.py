"""
Cache WAV 8 kHz pour l'IVR / repondeur (evite edge-tts + conversion a chaque appel).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from loguru import logger

from backend.voice.audio_utils import export_wav_8k_8bit, trim_leading_trailing_silence

if TYPE_CHECKING:
    from backend.core.config import Config
    from backend.voice.synthesis import VoiceSynthesis


def ivr_content_hash(text: str, engine: str, voice: str, speech_rate: str = "+0%", speech_pitch: str = "+0Hz") -> str:
    raw = f"{engine}\0{voice}\0{speech_rate}\0{speech_pitch}\0{text.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class IvrAudioCache:
    """Genere et reutilise des WAV 8 kHz prets pour le modem."""

    def __init__(self, config: "Config", synthesis: "VoiceSynthesis") -> None:
        self.config = config
        self.synthesis = synthesis
        base = Path(config.base_path) if config.base_path else Path(".")
        self.cache_dir = base / "ivr_wav"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, basename: str) -> Path:
        return self.cache_dir / f"{basename}.meta.json"

    def _wav_path(self, basename: str) -> Path:
        return self.cache_dir / f"{basename}.wav"

    def _speech_rate(self) -> str:
        return (getattr(self.config, "edge_tts_rate", None) or "+0%").strip()

    def _speech_pitch(self) -> str:
        return (getattr(self.config, "edge_tts_pitch", None) or "+0Hz").strip()

    def _current_hash(self, text: str) -> str:
        engine = self.synthesis.engine
        voice = getattr(self.config, "edge_tts_voice", "") or ""
        return ivr_content_hash(
            text,
            engine,
            voice,
            self._speech_rate(),
            self._speech_pitch(),
        )

    def is_fresh(self, basename: str, text: str) -> bool:
        wav = self._wav_path(basename)
        meta = self._meta_path(basename)
        if not wav.exists() or not meta.exists():
            return False
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            return data.get("hash") == self._current_hash(text)
        except (OSError, json.JSONDecodeError, KeyError):
            return False

    def get_if_fresh(self, text: str, basename: str) -> Optional[Path]:
        if self.is_fresh(basename, text):
            return self._wav_path(basename)
        return None

    async def ensure(self, text: str, basename: str) -> Optional[Path]:
        if not text.strip():
            return None
        wav = self._wav_path(basename)
        if self.is_fresh(basename, text):
            logger.debug("Cache IVR a jour: {}", wav.name)
            return wav

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub manquant pour le cache IVR")
            return None

        temp = await self.synthesis.speak(
            text,
            rate=self._speech_rate(),
            pitch=self._speech_pitch(),
        )
        if not temp or not Path(temp).exists():
            logger.warning("TTS echoue pour cache IVR {}", basename)
            return None

        try:
            segment = AudioSegment.from_file(str(temp))
            thresh = -40.0
            if segment.dBFS != float("-inf"):
                thresh = max(-45.0, segment.dBFS - 18.0)
            segment = trim_leading_trailing_silence(segment, silence_threshold=thresh, padding_ms=15)
            export_wav_8k_8bit(segment, wav, normalize=True)
            self._meta_path(basename).write_text(
                json.dumps(
                    {"hash": self._current_hash(text), "text": text.strip()},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logger.info("Cache IVR genere: {} ({} octets)", wav.name, wav.stat().st_size)
            return wav
        except Exception as e:
            logger.exception("Erreur cache IVR {}: {}", basename, e)
            return None
