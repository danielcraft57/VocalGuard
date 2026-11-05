"""
Filtre ambiance (TV, musique, smartphone) avant STT live.

Combine bande voix, WebRTC VAD (si installe), plancher de bruit adaptatif.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

AUDIO_RATE = 16000


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or ("1" if default else "0")).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def bandpass_voice_mono(mono: np.ndarray, sample_rate: int = AUDIO_RATE) -> np.ndarray:
    """
    Filtre passe-bande type telephonie (300-3400 Hz) pour attenuer basse musique / rumble.

    @param mono Echantillons float32.
    @param sample_rate Hz.
    @returns Signal filtre.
    """
    if len(mono) < 32:
        return mono
    low = 300.0
    high = min(3400.0, sample_rate * 0.45)
    spec = np.fft.rfft(mono.astype(np.float64))
    freqs = np.fft.rfftfreq(len(mono), d=1.0 / sample_rate)
    mask = (freqs >= low) & (freqs <= high)
    spec[~mask] = 0.0
    out = np.fft.irfft(spec, n=len(mono)).astype(np.float32)
    return np.clip(out, -1.0, 1.0)


def env_float(name: str, default: float) -> float:
    """Lecture float depuis os.environ."""
    return _env_float(name, default)


class AmbientSpeechGate:
    """
    Detecte la parole proche (micro casque) vs ambiance (TV, HP, piece).

    @param enabled Active le filtre (VG_STUDIO_NOISE_GATE).
    """

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        self.enabled = (
            _env_bool("VG_STUDIO_NOISE_GATE", True) if enabled is None else enabled
        )
        self._noise_floor = _env_float("VG_LIVE_NOISE_FLOOR", 0.004)
        self._snr_margin = _env_float("VG_LIVE_GATE_SNR", 2.2)
        self._band_ratio_min = _env_float("VG_LIVE_BAND_RATIO", 0.42)
        self._crest_min = _env_float("VG_LIVE_CREST_MIN", 2.0)
        self._webrtc = None
        self._webrtc_aggr = int(_env_float("VG_WEBRTC_VAD_AGGR", 2))
        if self.enabled and _env_bool("VG_LIVE_WEBRTC_VAD", True):
            try:
                import webrtcvad

                self._webrtc = webrtcvad.Vad(max(0, min(3, self._webrtc_aggr)))
            except Exception:
                self._webrtc = None

    def reset(self) -> None:
        """Reinitialise le plancher de bruit."""
        self._noise_floor = _env_float("VG_LIVE_NOISE_FLOOR", 0.004)

    def _rms(self, mono: np.ndarray) -> float:
        if len(mono) < 1:
            return 0.0
        return float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))

    def _webrtc_speech(self, mono_f32: np.ndarray) -> Optional[bool]:
        if self._webrtc is None or len(mono_f32) < 480:
            return None
        pcm = np.clip(mono_f32, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16).tobytes()
        frame_len = 480
        votes = 0
        total = 0
        for i in range(0, len(pcm16) - frame_len * 2 + 1, frame_len * 2):
            frame = pcm16[i : i + frame_len * 2]
            if len(frame) < frame_len * 2:
                break
            try:
                if self._webrtc.is_speech(frame, AUDIO_RATE):
                    votes += 1
            except Exception:
                return None
            total += 1
        if total == 0:
            return None
        return votes >= max(1, total // 2)

    def is_speech_block(self, mono_f32: np.ndarray) -> bool:
        """
        True si le bloc ressemble a de la parole proche (pas seulement du bruit ambient).

        @param mono_f32 Mono float32 16 kHz.
        @returns Decision gate.
        """
        if not self.enabled:
            return True
        filtered = bandpass_voice_mono(mono_f32)
        rms_all = self._rms(mono_f32)
        rms_band = self._rms(filtered)
        if rms_all < self._noise_floor * 0.5:
            self._noise_floor = min(
                self._noise_floor,
                rms_all * 0.95 + self._noise_floor * 0.05,
            )
            return False
        if rms_all < self._noise_floor * self._snr_margin:
            self._noise_floor = min(
                self._noise_floor * 0.998 + rms_all * 0.002,
                _env_float("VG_LIVE_NOISE_FLOOR", 0.004),
            )
            return False
        band_ratio = rms_band / (rms_all + 1e-9)
        if band_ratio < self._band_ratio_min:
            return False
        peak = float(np.max(np.abs(filtered))) if len(filtered) else 0.0
        crest = peak / (rms_band + 1e-9)
        if crest < self._crest_min and rms_all < self._noise_floor * (self._snr_margin + 1.5):
            return False
        webrtc = self._webrtc_speech(filtered)
        if webrtc is False:
            return False
        self._noise_floor = min(
            self._noise_floor * 0.995 + rms_all * 0.005,
            rms_all * 0.85,
        )
        return True

    def speech_ratio(self, mono: np.ndarray, *, block_samples: int = 800) -> float:
        """
        Part de blocs reconnus comme parole (0..1).

        @param mono Tour audio complet.
        @param block_samples Taille de fenetre (~50 ms a 16 kHz).
        @returns Ratio.
        """
        if not self.enabled or len(mono) < block_samples:
            return 1.0
        hits = 0
        total = 0
        for i in range(0, len(mono) - block_samples + 1, block_samples):
            if self.is_speech_block(mono[i : i + block_samples]):
                hits += 1
            total += 1
        return hits / max(1, total)

    def prepare_stt_chunk(self, mono: np.ndarray) -> Optional[np.ndarray]:
        """
        Retourne un chunk filtre pret STT, ou None si trop d'ambiance.

        @param mono Buffer mono float32.
        @returns Audio bande voix ou None.
        """
        if len(mono) < int(AUDIO_RATE * 0.3):
            return None
        filtered = bandpass_voice_mono(mono)
        if self.speech_ratio(filtered) < env_float("VG_LIVE_CHUNK_SPEECH_RATIO", 0.28):
            return None
        return filtered
