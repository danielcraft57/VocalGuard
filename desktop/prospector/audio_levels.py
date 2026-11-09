"""
Niveaux audio enregistrement / lecture (gain, limiteur doux).
"""

from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from desktop.modem_local_call import scale_pcm_s16le
from desktop.prospector.settings import (
    record_line_gain,
    record_line_min_crest,
    record_mic_gain,
    record_noise_gate_close_rms,
    record_noise_gate_rms,
)

RecordChannel = Literal["line", "mic"]

_GATE_HANGOVER_BUFFERS = 12


def pcm16_mono_crest(pcm16_mono: bytes) -> float:
    """
    Facteur de crete pic/RMS (parole typ. > 2, tonalite continue ~1.2..1.6).

    @param pcm16_mono Buffer mono s16le.
    @returns Rapport pic/RMS ou 0 si silence.
    """
    if not pcm16_mono:
        return 0.0
    arr = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float32)
    peak = float(np.max(np.abs(arr)))
    rms = float(np.sqrt(np.mean(arr * arr)))
    if rms < 8.0:
        return 0.0
    return peak / rms


def pcm16_mono_rms(pcm16_mono: bytes) -> float:
    """
    RMS normalise 0..1 d'un buffer PCM s16le mono.

    @param pcm16_mono Echantillons bruts.
    @returns RMS sur echelle float (typ. 0.001..0.3).
    """
    if not pcm16_mono:
        return 0.0
    arr = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(arr * arr)))

def pcm16_soft_limit(pcm16_mono: bytes, gain: float) -> bytes:
    """
    Applique gain puis limiteur ``tanh`` pour eviter une saturation brick-wall sur le WAV.

    @param pcm16_mono Buffer mono s16le.
    @param gain Facteur avant limiteur (typ. 0.3..0.5 ligne).
    @returns PCM re-quantifie.
    """
    if not pcm16_mono:
        return pcm16_mono
    g = max(0.05, min(1.5, float(gain)))
    arr = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float32) / 32768.0
    arr *= g
    knee = 2.2
    arr = np.tanh(arr * knee) / np.tanh(knee)
    out = np.clip(arr * 32767.0, -32768, 32767).astype(np.int16)
    return out.tobytes()


def record_line_apply_processor() -> bool:
    """
    Active porte-bruit + passe-haut sur le WAV ligne (desactive par defaut).

    ``VG_PROSPECTOR_RECORD_LINE_FILTER=1`` pour retrouver l'ancien comportement.
    """
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_LINE_FILTER") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def pcm16_for_recording(pcm16_mono: bytes, channel: RecordChannel) -> bytes:
    """
    Prepare un bloc pour ``DualMonoCallRecorder`` (gains Prospector).

    @param pcm16_mono Echantillons bruts du pont modem.
    @param channel ``line`` ou ``mic``.
    @returns PCM attenue et limite.
    """
    if channel == "line":
        if record_line_apply_processor():
            return LineRecordProcessor.shared().process(pcm16_mono)
        return pcm16_soft_limit(pcm16_mono, record_line_gain())
    return pcm16_soft_limit(pcm16_mono, record_mic_gain())


class LineRecordProcessor:
    """
    Traitement ligne pour WAV : porte-bruit + passe-haut leger + gain.

    Une instance partagee par thread d'appel suffit (un appel a la fois).
    """

    _shared: Optional["LineRecordProcessor"] = None

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Reinitialise l'etat filtre entre deux appels."""
        self._hp_x = 0.0
        self._hp_y = 0.0
        self._gate_open = False
        self._hangover = 0
        self._calib_rms: list[float] = []
        self._noise_floor = 0.0

    def observe_line(self, pcm16_mono: bytes) -> None:
        """
        Mesure le plancher ligne (sonnerie / souffle) avant ouverture WAV.

        @param pcm16_mono Trame brute modem.
        """
        if not pcm16_mono:
            return
        crest = pcm16_mono_crest(pcm16_mono)
        if crest >= record_line_min_crest() * 1.12:
            return
        rms = pcm16_mono_rms(pcm16_mono)
        if rms < 0.002:
            return
        self._calib_rms.append(rms)
        if len(self._calib_rms) > 60:
            self._calib_rms.pop(0)
        self._noise_floor = float(np.median(self._calib_rms))

    def _open_threshold(self) -> float:
        """Seuil adaptatif au plancher mesure sur la sonnerie."""
        base = record_noise_gate_rms()
        if self._noise_floor > 0:
            return max(base, self._noise_floor * 1.45 + 0.01)
        return base

    @classmethod
    def shared(cls) -> "LineRecordProcessor":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    def process(self, pcm16_mono: bytes) -> bytes:
        """
        Attenue le souffle de ligne et n'enregistre que la parole utile.

        @param pcm16_mono PCM brut modem -> casque.
        @returns Bloc pret pour ``feed_line``.
        """
        if not pcm16_mono:
            return pcm16_mono
        arr = np.frombuffer(pcm16_mono, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(arr * arr)))
        crest = pcm16_mono_crest(pcm16_mono)
        min_crest = record_line_min_crest()
        if crest < min_crest:
            if self._hangover > 0:
                self._hangover = max(0, self._hangover - 1)
            return np.zeros(len(arr), dtype=np.int16).tobytes()
        open_th = self._open_threshold()
        close_th = min(open_th * 0.55, record_noise_gate_close_rms())
        if self._gate_open:
            if rms < close_th:
                self._hangover = max(0, self._hangover - 1)
                if self._hangover <= 0:
                    self._gate_open = False
            else:
                self._hangover = _GATE_HANGOVER_BUFFERS
        elif rms >= open_th and crest >= min_crest:
            self._gate_open = True
            self._hangover = _GATE_HANGOVER_BUFFERS
        if not self._gate_open and self._hangover <= 0:
            return np.zeros(len(arr), dtype=np.int16).tobytes()
        # Passe-haut (souffle basse frequence)
        alpha = 0.992
        out = np.empty_like(arr)
        x_prev, y_prev = self._hp_x, self._hp_y
        for i, x in enumerate(arr):
            y = alpha * (y_prev + x - x_prev)
            out[i] = y
            x_prev, y_prev = x, y
        self._hp_x, self._hp_y = x_prev, y_prev
        pcm = np.clip(out * 32768.0, -32768, 32767).astype(np.int16).tobytes()
        return pcm16_soft_limit(pcm, record_line_gain())


def analyze_wav_stereo(path: Path) -> dict[str, float]:
    """
    Mesure peak / RMS / taux de saturation par canal.

    @param path Fichier WAV.
    @returns Dict avec cles ``L_peak``, ``L_rms``, ``L_clip_pct``, etc.
    """
    out: dict[str, float] = {}
    try:
        with wave.open(str(path), "rb") as wf:
            nch = wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
    except (OSError, wave.Error):
        return out
    if not raw:
        return out
    arr = np.frombuffer(raw, dtype=np.int16)
    if nch >= 2:
        arr = arr.reshape(-1, nch)
    else:
        arr = arr.reshape(-1, 1)
    names = ("L", "R", "C")[: arr.shape[1]]
    for i, name in enumerate(names):
        x = arr[:, i].astype(np.float64)
        if x.size == 0:
            continue
        peak = float(np.max(np.abs(x)))
        rms = float(np.sqrt(np.mean(x * x)))
        clip = float(np.mean(np.abs(x) >= 32000) * 100.0)
        out[f"{name}_peak"] = peak
        out[f"{name}_rms"] = rms
        out[f"{name}_clip_pct"] = clip
    return out


def normalize_playback_mono(audio: np.ndarray, *, target_peak: float = 0.85) -> np.ndarray:
    """
    Baisse le gain si un ancien enregistrement etait sature a l'export.

    @param audio Float mono -1..1.
    @param target_peak Plafond apres normalisation.
    @returns Signal ajuste.
    """
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak <= 1e-6:
        return audio
    if peak <= target_peak:
        return audio
    return audio * (target_peak / peak)
