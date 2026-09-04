"""
VAD / silence de fin de tour (RMS local, node14).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.voice.audio_utils import pcm_s16le_rms


@dataclass
class TurnVadConfig:
    """
    Seuils silence conversation vs messagerie.

    @param speech_rms_threshold RMS mini pour considerer de la parole.
    @param turn_silence_ms Silence court = fin de tour.
    @param message_silence_ms Silence long = fin messagerie (hors boucle tour).
    @param hangover_ms Silence reduit apres commit belief (non utilise ici, info).
    """

    speech_rms_threshold: float = 350.0
    turn_silence_ms: float = 600.0
    message_silence_ms: float = 3500.0
    hangover_ms: float = 200.0


class TurnVad:
    """
    Detecte fin de tour a partir de frames PCM s16le.

    Ne demarre le chrono silence qu'apres avoir entendu de la parole.
    """

    def __init__(self, config: Optional[TurnVadConfig] = None) -> None:
        """
        @param config Seuils RMS / durees.
        """
        self.config = config or TurnVadConfig()
        self.heard_speech = False
        self._silence_ms = 0.0
        self.ended = False

    def reset(self) -> None:
        """Remet l'etat pour un nouveau tour."""
        self.heard_speech = False
        self._silence_ms = 0.0
        self.ended = False

    def feed(self, pcm_s16le: bytes, *, frame_ms: float) -> bool:
        """
        Ingere une frame audio.

        @param pcm_s16le Buffer PCM mono 16-bit LE.
        @param frame_ms Duree de la frame en millisecondes.
        @returns True si fin de tour (silence apres parole).
        """
        if self.ended:
            return True
        rms = pcm_s16le_rms(pcm_s16le)
        cfg = self.config
        if rms >= cfg.speech_rms_threshold:
            self.heard_speech = True
            self._silence_ms = 0.0
            return False
        if not self.heard_speech:
            return False
        self._silence_ms += max(0.0, float(frame_ms))
        if self._silence_ms >= cfg.turn_silence_ms:
            self.ended = True
            return True
        return False

    def feed_buffer(
        self,
        pcm_s16le: bytes,
        *,
        sample_rate: int = 16000,
        frame_ms: float = 20.0,
    ) -> bool:
        """
        Decoupe un buffer en frames et alimente le VAD.

        @param pcm_s16le PCM complet.
        @param sample_rate Taux d'echantillonnage.
        @param frame_ms Taille de frame.
        @returns True si fin de tour detectee.
        """
        bytes_per_ms = max(1, int(sample_rate * 2 / 1000))
        frame_bytes = max(2, int(bytes_per_ms * frame_ms))
        if frame_bytes % 2:
            frame_bytes += 1
        for i in range(0, len(pcm_s16le), frame_bytes):
            chunk = pcm_s16le[i : i + frame_bytes]
            if len(chunk) < 2:
                continue
            if self.feed(chunk, frame_ms=frame_ms):
                return True
        return self.ended

    @property
    def silence_ms(self) -> float:
        """Silence cumule depuis la derniere parole."""
        return self._silence_ms
