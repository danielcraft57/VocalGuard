"""
Lecture des enregistrements d'appels (WAV stereo L=ligne, R=micro).
"""

from __future__ import annotations

import threading
import wave
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, QThread, Signal

from desktop.audio_core import normalize_device_index, output_device_candidates
from desktop.prospector.audio_levels import normalize_playback_mono

ChannelMode = Literal["stereo", "line", "mic"]


def load_wav_mono(path: Path, channel: ChannelMode) -> tuple[np.ndarray, int]:
    """
    Charge un WAV et retourne un signal mono float32.

    @param path Fichier .wav.
    @param channel Mode d'ecoute.
    @returns (echantillons -1..1, sample_rate).
    """
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise ValueError(f"Format WAV non supporte (sampwidth={sw}, attendu 16 bits).")
    arr = np.frombuffer(raw, dtype=np.int16)
    if nch >= 2:
        arr = arr.reshape(-1, nch)
        if channel == "line":
            mono = arr[:, 0].astype(np.float32)
        elif channel == "mic":
            mono = arr[:, min(1, nch - 1)].astype(np.float32)
        else:
            mono = (
                arr[:, 0].astype(np.float32) + arr[:, min(1, nch - 1)].astype(np.float32)
            ) * 0.5
    else:
        mono = arr.astype(np.float32)
    mono /= 32768.0
    mono = np.clip(mono, -1.0, 1.0)
    mono = normalize_playback_mono(mono)
    return mono, rate


def wav_duration_seconds(path: Path) -> float:
    """
    Duree utile d'un WAV.

    @param path Chemin fichier.
    @returns Secondes ou 0 si illisible.
    """
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except (wave.Error, OSError):
        return 0.0


class _WavPlayWorker(QThread):
    """Thread Qt pour PortAudio (evite conflits avec l'UI)."""

    tick = Signal(float, float)
    failed = Signal(str)

    def __init__(
        self,
        audio: np.ndarray,
        rate: int,
        devices: list[Optional[int]],
        stop_event: threading.Event,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._audio = audio
        self._rate = rate
        self._devices = devices
        self._stop = stop_event
        self._total_s = len(audio) / float(rate) if rate else 0.0

    def run(self) -> None:
        """Joue le buffer sur la premiere sortie utilisable."""
        last_err: Optional[Exception] = None
        for dev in self._devices:
            if self._stop.is_set():
                return
            try:
                sd.play(self._audio, self._rate, device=dev)
                elapsed = 0.0
                step = 0.08
                while elapsed < self._total_s and not self._stop.is_set():
                    sd.sleep(int(step * 1000))
                    elapsed += step
                    self.tick.emit(min(elapsed, self._total_s), self._total_s)
                if self._stop.is_set():
                    sd.stop()
                    return
                sd.wait()
                self.tick.emit(self._total_s, self._total_s)
                return
            except Exception as exc:
                last_err = exc
                sd.stop()
        if last_err is not None:
            self.failed.emit(str(last_err))


class CallWavPlayer(QObject):
    """
    Lecteur historique Prospector (QThread + sounddevice).

    @signal position_changed Position courante et duree totale en secondes.
    @signal state_changed True pendant la lecture.
    @signal error Message utilisateur.
    """

    position_changed = Signal(float, float)
    state_changed = Signal(bool)
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._worker: Optional[_WavPlayWorker] = None
        self._playing = False
        self._total_s = 0.0

    def is_playing(self) -> bool:
        """True si une lecture est en cours."""
        return self._playing

    def play(
        self,
        path: Path,
        *,
        channel: ChannelMode = "stereo",
        output_device: Optional[int] = None,
        gain: float = 0.75,
    ) -> None:
        """
        Demarre la lecture (arrete la precedente).

        @param path Fichier WAV enregistre.
        @param channel Ligne, micro ou mix stereo.
        @param output_device Index sounddevice sortie.
        @param gain Volume 0.05..1.
        """
        self.stop(wait=True)
        if not path.is_file():
            self.error.emit(f"Fichier introuvable : {path}")
            return
        try:
            audio, rate = load_wav_mono(path, channel)
        except (OSError, wave.Error, ValueError) as exc:
            self.error.emit(str(exc))
            return
        if audio.size == 0:
            self.error.emit("Fichier vide (0 echantillon).")
            return
        self._total_s = len(audio) / float(rate) if rate else 0.0
        g = max(0.05, min(1.0, float(gain)))
        audio = (audio * g).astype(np.float32)
        preferred = normalize_device_index(output_device, kind="output")
        devices = output_device_candidates(preferred)
        if not devices:
            devices = [None]

        self._stop.clear()
        self._playing = True
        self.state_changed.emit(True)

        worker = _WavPlayWorker(audio, rate, devices, self._stop, self)
        worker.tick.connect(self.position_changed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def _on_worker_failed(self, msg: str) -> None:
        self.error.emit(msg)
        self._on_worker_finished()

    def _on_worker_finished(self) -> None:
        self._playing = False
        self.state_changed.emit(False)
        self.finished.emit()
        self._worker = None

    def stop(self, *, wait: bool = True) -> None:
        """Arrete la lecture en cours."""
        self._stop.set()
        try:
            sd.stop()
        except Exception:
            pass
        worker = self._worker
        if wait and worker is not None and worker.isRunning():
            worker.wait(3000)
        self._playing = False
        self.state_changed.emit(False)
