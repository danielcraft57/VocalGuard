#!/usr/bin/env python3
"""
Détection d'activité vocale sur PCM 8 kHz 8-bit (flux modem / fichier WAV converti).

Émet des événements **speech_start** / **speech_end** selon seuil d'énergie (MAD ou RMS),
maintien minimal et **hangover** (silence avant fin de parole).

Ce n'est pas un modèle ML : simple seuillage adapté au câble téléphonique et au bruit de ligne.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional

from labcore.pcm_metrics import (
    frame_length_bytes,
    iter_complete_frames,
    mean_abs_deviation_u8,
    rms_u8_centered,
)


class VaKind(str, Enum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"


@dataclass(frozen=True)
class VaEvent:
    """Événement « ça parle » / fin de parole sur le flux analysé."""

    kind: VaKind
    """Offset (octets PCM) depuis le dernier ``reset`` : fin de la trame qui a déclenché l'événement."""
    offset_end_bytes: int
    """Métrique sur la dernière trame utile (MAD ou RMS)."""
    metric: float


MetricName = Literal["mad", "rms"]


def _metric(frame: bytes, name: MetricName) -> float:
    if name == "rms":
        return rms_u8_centered(frame)
    return mean_abs_deviation_u8(frame)


class SpeechActivityDetector:
    """
    Analyse un flux par blocs : appelez ``feed`` avec des morceaux arbitraires d'octets PCM u8.

    - **speech_start** : métrique >= seuil pendant au moins ``min_speech_ms`` consécutifs.
    - **speech_end** : métrique < seuil pendant ``hangover_ms`` alors qu'on était en parole.

    Paramètres **adaptive** (optionnel) : un plancher de bruit (EMA) est mis à jour sur les
    trames « calmes '' (métrique < ``adaptive_learn_max``) ; le seuil effectif devient
    ``max(threshold, noise_floor * noise_ratio)``.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 8000,
        frame_ms: float = 20.0,
        threshold: float = 18.0,
        min_speech_ms: float = 120.0,
        hangover_ms: float = 400.0,
        metric: MetricName = "mad",
        adaptive: bool = False,
        noise_ratio: float = 3.0,
        noise_learn_alpha: float = 0.08,
        adaptive_learn_max: float = 25.0,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.frame_ms = float(frame_ms)
        self.threshold = float(threshold)
        self.min_speech_ms = float(min_speech_ms)
        self.hangover_ms = float(hangover_ms)
        self.metric: MetricName = metric
        self.adaptive = bool(adaptive)
        self.noise_ratio = float(noise_ratio)
        self.noise_learn_alpha = float(noise_learn_alpha)
        self.adaptive_learn_max = float(adaptive_learn_max)
        self._frame_len = frame_length_bytes(self.sample_rate, self.frame_ms)
        self._buf = bytearray()
        self._in_speech = False
        self._above_ms = 0.0
        self._hang_ms = 0.0
        self._bytes_framed = 0
        self._noise_floor: Optional[float] = None

    @property
    def frame_len(self) -> int:
        return self._frame_len

    def reset(self) -> None:
        self._buf.clear()
        self._in_speech = False
        self._above_ms = 0.0
        self._hang_ms = 0.0
        self._bytes_framed = 0
        self._noise_floor = None

    def _effective_threshold(self, frame_metric: float) -> float:
        if not self.adaptive:
            return self.threshold
        a = self.noise_learn_alpha
        if self._noise_floor is None:
            self._noise_floor = frame_metric
        elif frame_metric <= self.adaptive_learn_max:
            self._noise_floor = (1.0 - a) * self._noise_floor + a * frame_metric
        return max(self.threshold, (self._noise_floor or 0.0) * self.noise_ratio)

    def feed(self, data: bytes) -> list[VaEvent]:
        out: list[VaEvent] = []
        for frame in iter_complete_frames(self._buf, data, self._frame_len):
            self._bytes_framed += self._frame_len
            m = _metric(frame, self.metric)
            thr = self._effective_threshold(m)
            fms = self.frame_ms

            if m >= thr:
                self._above_ms += fms
                self._hang_ms = 0.0
                if not self._in_speech and self._above_ms >= self.min_speech_ms:
                    self._in_speech = True
                    out.append(
                        VaEvent(
                            kind=VaKind.SPEECH_START,
                            offset_end_bytes=self._bytes_framed,
                            metric=m,
                        )
                    )
            else:
                self._above_ms = 0.0
                if self._in_speech:
                    self._hang_ms += fms
                    if self._hang_ms >= self.hangover_ms:
                        self._in_speech = False
                        self._hang_ms = 0.0
                        out.append(
                            VaEvent(
                                kind=VaKind.SPEECH_END,
                                offset_end_bytes=self._bytes_framed,
                                metric=m,
                            )
                        )

        return out
