"""
Sons UI Prospector (beeps synthetises, volume, sonnerie entrante).
"""

from __future__ import annotations

import math
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from desktop.audio_core import AUDIO_RATE, output_device_candidates
from desktop.prospector.ui_prefs import load_prefs, save_prefs


class ProspectorSounds:
    """
    Moteur de retours sonores (thread dedie, volume global).

    @param output_device_provider Callback index sortie casque (optionnel).
    """

    def __init__(
        self,
        output_device_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        self._output_device_provider = output_device_provider or (lambda: None)
        self._volume = 0.65
        self._muted = False
        self._ring_stop = threading.Event()
        self._ring_thread: Optional[threading.Thread] = None
        self._load_prefs()

    @property
    def volume(self) -> float:
        """Volume linear 0..1."""
        return 0.0 if self._muted else self._volume

    @property
    def volume_percent(self) -> int:
        """Volume affichage 0..100."""
        return int(round(self._volume * 100))

    @property
    def muted(self) -> bool:
        """True si son coupe."""
        return self._muted

    def set_output_device_provider(self, provider: Callable[[], Optional[int]]) -> None:
        """Met a jour la sortie audio (casque parametres)."""
        self._output_device_provider = provider

    def set_volume_percent(self, percent: int) -> None:
        """
        Regle le volume UI.

        @param percent Entier 0..100.
        """
        self._volume = max(0.0, min(1.0, percent / 100.0))
        self._save_prefs()

    def set_muted(self, muted: bool) -> None:
        """Active ou coupe tous les sons."""
        self._muted = muted
        if muted:
            self.stop_ring()
        self._save_prefs()

    def play(self, kind: str) -> None:
        """
        Joue un jingle court (connect, hangup, success, error, notify).

        @param kind Identifiant du son.
        """
        if self._muted or self._volume <= 0.001:
            return
        threading.Thread(target=self._play_once, args=(kind,), daemon=True).start()

    def start_ring(self) -> None:
        """Sonnerie entrante en boucle jusqu'a stop_ring."""
        if self._muted or self._volume <= 0.001:
            return
        self.stop_ring()
        self._ring_stop.clear()
        self._ring_thread = threading.Thread(target=self._ring_loop, daemon=True)
        self._ring_thread.start()

    def stop_ring(self) -> None:
        """Arrete la sonnerie entrante."""
        self._ring_stop.set()

    def play_test_beep(self) -> None:
        """Bip de test sur la sortie configuree."""
        self.play("test")

    def _load_prefs(self) -> None:
        data = load_prefs()
        try:
            self._volume = max(0.0, min(1.0, float(data.get("ui_volume", self._volume))))
            self._muted = bool(data.get("muted", False))
        except (TypeError, ValueError):
            pass

    def _save_prefs(self) -> None:
        save_prefs(ui_volume=round(self._volume, 2), muted=self._muted)

    def _output_device(self) -> Optional[int]:
        try:
            return self._output_device_provider()
        except Exception:
            return None

    def _gain(self) -> float:
        return max(0.02, min(1.0, self._volume * 0.85))

    def _tone(
        self,
        freq: float,
        duration_s: float,
        *,
        fade_ms: float = 12.0,
    ) -> np.ndarray:
        n = int(AUDIO_RATE * duration_s)
        t = np.arange(n, dtype=np.float64) / AUDIO_RATE
        wave = np.sin(2 * math.pi * freq * t)
        fade_n = max(1, int(AUDIO_RATE * fade_ms / 1000.0))
        env = np.ones(n, dtype=np.float64)
        env[:fade_n] = np.linspace(0.0, 1.0, fade_n)
        env[-fade_n:] = np.linspace(1.0, 0.0, fade_n)
        return (self._gain() * wave * env).astype(np.float32)

    def _concat(self, parts: list[np.ndarray]) -> np.ndarray:
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts)

    def _wave_for(self, kind: str) -> np.ndarray:
        if kind == "test":
            return self._tone(523.25, 0.22)
        if kind == "connect":
            return self._concat(
                [
                    self._tone(523.25, 0.08),
                    self._tone(659.25, 0.1),
                    self._tone(783.99, 0.14),
                ]
            )
        if kind == "hangup":
            return self._concat(
                [
                    self._tone(440.0, 0.1),
                    self._tone(330.0, 0.14),
                ]
            )
        if kind == "success":
            return self._concat(
                [
                    self._tone(587.33, 0.09),
                    self._tone(739.99, 0.12),
                ]
            )
        if kind == "error":
            return self._tone(220.0, 0.28)
        if kind == "notify":
            return self._tone(880.0, 0.06)
        return self._tone(440.0, 0.08)

    def _play_buffer(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        dev = self._output_device()
        last_err: Optional[Exception] = None
        for candidate in output_device_candidates(dev):
            try:
                sd.play(audio, AUDIO_RATE, device=candidate)
                sd.wait()
                return
            except Exception as exc:
                last_err = exc
        _ = last_err

    def _play_once(self, kind: str) -> None:
        if self._muted:
            return
        self._play_buffer(self._wave_for(kind))

    def _ring_loop(self) -> None:
        while not self._ring_stop.is_set():
            chunk = self._concat(
                [
                    self._tone(440.0, 0.35),
                    np.zeros(int(AUDIO_RATE * 0.12), dtype=np.float32),
                    self._tone(480.0, 0.35),
                    np.zeros(int(AUDIO_RATE * 0.35), dtype=np.float32),
                ]
            )
            self._play_buffer(chunk)
            if self._ring_stop.wait(0.05):
                break
