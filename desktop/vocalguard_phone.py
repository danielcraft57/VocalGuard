#!/usr/bin/env python3
"""
VocalGuard Phone — client bureau Windows (micro-casque + modem sur node14).

Usage:
  python desktop/vocalguard_phone.py
"""

from __future__ import annotations

import asyncio
import math
import os
import queue
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen

import httpx
import numpy as np
import sounddevice as sd
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import websockets
except ImportError:
    print("Installez websockets: pip install websockets")
    sys.exit(1)

DEFAULT_API = os.environ.get("VG_PHONE_API", "http://node14.lan:8090/api/v1").rstrip("/")
DEFAULT_WS = os.environ.get("VG_PHONE_WS", "ws://node14.lan:8090").rstrip("/")
RECORDINGS_DIR = Path(
    os.environ.get(
        "VG_PHONE_RECORDINGS",
        str(Path.home() / "Documents" / "VocalGuard" / "recordings" / "desktop"),
    )
)
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_RATE = 16000
BLOCK = 320  # 20 ms @ 16 kHz
DIAL_TONE_HZ = 425.0
DIAL_TONE_GAIN = 0.12


def make_tone(freq: float, duration_sec: float, gain: float = 0.25) -> np.ndarray:
    n = max(1, int(AUDIO_RATE * duration_sec))
    t = np.arange(n, dtype=np.float64) / AUDIO_RATE
    fade = min(int(AUDIO_RATE * 0.02), n // 4)
    env = np.ones(n)
    if fade > 0:
        env[:fade] = np.linspace(0, 1, fade)
        env[-fade:] = np.linspace(1, 0, fade)
    return (gain * env * np.sin(2 * math.pi * freq * t)).astype(np.float32)


def pcm16_from_f32(arr: np.ndarray) -> bytes:
    clipped = np.clip(arr, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


class AudioDeviceHelper:
    """Liste et sélection des périphériques Windows (sounddevice)."""

    @staticmethod
    def list_devices() -> tuple[list[str], list[str], dict[str, int], dict[str, int]]:
        in_names: list[str] = []
        out_names: list[str] = []
        in_map: dict[str, int] = {}
        out_map: dict[str, int] = {}
        for i, d in enumerate(sd.query_devices()):
            name = d["name"]
            if d["max_input_channels"] > 0:
                label = f"[{i}] {name}"
                in_names.append(label)
                in_map[label] = i
            if d["max_output_channels"] > 0:
                label = f"[{i}] {name}"
                out_names.append(label)
                out_map[label] = i
        return in_names, out_names, in_map, out_map

    @staticmethod
    def default_labels(
        in_map: dict[str, int], out_map: dict[str, int]
    ) -> tuple[Optional[str], Optional[str]]:
        try:
            din, dout = sd.default.device
        except Exception:
            return None, None
        in_label = next((k for k, v in in_map.items() if v == din), None)
        out_label = next((k for k, v in out_map.items() if v == dout), None)
        return in_label, out_label

    @staticmethod
    def find_headset_labels(
        in_map: dict[str, int], out_map: dict[str, int]
    ) -> tuple[Optional[str], Optional[str]]:
        """Cherche un casque Bluetooth (Hands-Free / Casque)."""
        in_label = out_label = None
        for label in in_map:
            low = label.lower()
            if "casque" in low or "hands-free" in low or "headset" in low:
                in_label = label
                break
        for label in out_map:
            low = label.lower()
            if "casque" in low or "hands-free" in low or "headset" in low:
                out_label = label
                break
        return in_label, out_label

    @staticmethod
    def play_test_speaker(device: Optional[int], on_done: Callable[[str], None]) -> None:
        def worker() -> None:
            try:
                tone = make_tone(440.0, 0.35, 0.35)
                pause = np.zeros(int(AUDIO_RATE * 0.12), dtype=np.float32)
                dial = make_tone(DIAL_TONE_HZ, 1.2, DIAL_TONE_GAIN)
                signal = np.concatenate([tone, pause, tone, pause, dial])
                sd.play(signal, samplerate=AUDIO_RATE, device=device, blocking=True)
                on_done("Test casque OK (bip + tonalité 425 Hz)")
            except Exception as exc:
                on_done(f"Test casque échoué: {exc}")

        threading.Thread(target=worker, daemon=True, name="test_spk").start()

    @staticmethod
    def test_microphone(
        device: Optional[int],
        play_on: Optional[int],
        on_level: Callable[[float], None],
        on_done: Callable[[str], None],
    ) -> None:
        def worker() -> None:
            try:
                duration = 3.0
                on_done("Enregistrement micro 3 s… parlez maintenant")
                rec = sd.rec(
                    int(duration * AUDIO_RATE),
                    samplerate=AUDIO_RATE,
                    channels=1,
                    dtype="float32",
                    device=device,
                )
                for i in range(int(duration * 10)):
                    time.sleep(0.1)
                    end = min(rec.shape[0], (i + 1) * int(AUDIO_RATE / 10))
                    chunk = rec[:end]
                    if chunk.size:
                        level = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                        on_level(min(1.0, level * 12))
                sd.wait()
                peak = float(np.max(np.abs(rec)))
                rms = float(np.sqrt(np.mean(rec.astype(np.float64) ** 2)))
                on_level(0.0)
                if peak < 0.002:
                    on_done("Micro trop faible ou mauvais périphérique — choisissez le casque BT")
                    return
                on_done(f"Micro OK (niveau {rms:.3f}) — lecture dans le casque…")
                sd.play(rec, samplerate=AUDIO_RATE, device=play_on, blocking=True)
                on_done(f"Test micro terminé (niveau max {peak:.2f})")
            except Exception as exc:
                on_level(0.0)
                on_done(f"Test micro échoué: {exc}")

        threading.Thread(target=worker, daemon=True, name="test_mic").start()


def pcm16_rms_level(pcm: bytes) -> float:
    """Niveau RMS normalisé 0..1 pour PCM s16le mono."""
    if not pcm or len(pcm) < 2:
        return 0.0
    arr = np.frombuffer(pcm, dtype=np.int16)
    if arr.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))
    return min(1.0, rms / 8000.0)


class LiveAudioStats:
    """Compteurs thread-safe : niveaux ligne/micro + débit octets/s."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.line_level = 0.0
        self.mic_level = 0.0
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._rx_bytes_prev = 0
        self._tx_bytes_prev = 0
        self._last_tick = time.monotonic()
        self.rx_kbps = 0.0
        self.tx_kbps = 0.0
        self.connected = False

    def note_rx(self, pcm: bytes) -> None:
        with self._lock:
            self._rx_bytes += len(pcm)
            self.line_level = max(self.line_level * 0.55, pcm16_rms_level(pcm))

    def note_tx(self, pcm: bytes) -> None:
        with self._lock:
            self._tx_bytes += len(pcm)
            self.mic_level = max(self.mic_level * 0.55, pcm16_rms_level(pcm))

    def set_connected(self, ok: bool) -> None:
        with self._lock:
            self.connected = ok

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            dt = max(0.05, now - self._last_tick)
            rx_delta = self._rx_bytes - self._rx_bytes_prev
            tx_delta = self._tx_bytes - self._tx_bytes_prev
            self.rx_kbps = (rx_delta * 8.0) / (dt * 1000.0)
            self.tx_kbps = (tx_delta * 8.0) / (dt * 1000.0)
            self._rx_bytes_prev = self._rx_bytes
            self._tx_bytes_prev = self._tx_bytes
            self._last_tick = now
            # décroissance douce des barres
            self.line_level *= 0.82
            self.mic_level *= 0.82
            return {
                "line": self.line_level,
                "mic": self.mic_level,
                "rx_kbps": self.rx_kbps,
                "tx_kbps": self.tx_kbps,
                "rx_total": self._rx_bytes,
                "tx_total": self._tx_bytes,
                "connected": self.connected,
            }


class PlaybackEngine:
    """Sortie audio callback (file PCM int16 mono 16 kHz) avec prebuffer anti-saccades."""

    def __init__(self, device: Optional[int]) -> None:
        self.device = device
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stream: Optional[sd.RawOutputStream] = None
        self._dial_phase = 0.0
        self._dial_active = False
        self._remote_seen = False
        self._primed = False
        # ~180 ms de prebuffer avant de commencer a jouer la ligne
        self._prebuffer_bytes = int(AUDIO_RATE * 0.18) * 2
        # Plafond ~500 ms : au-dela on jette le plus vieux pour rattraper
        self._max_buf_bytes = int(AUDIO_RATE * 0.50) * 2

    def start(self) -> None:
        def callback(outdata, frames, time_info, status) -> None:
            need = frames * 2
            out = np.zeros(frames, dtype=np.int16)
            with self._lock:
                if self._primed and len(self._buf) >= need:
                    chunk = self._buf[:need]
                    del self._buf[:need]
                    out = np.frombuffer(chunk, dtype=np.int16).copy()
                elif self._dial_active and not self._primed:
                    t = np.arange(frames, dtype=np.float64)
                    ph = self._dial_phase
                    samp = (
                        DIAL_TONE_GAIN
                        * 32767
                        * np.sin(2 * math.pi * DIAL_TONE_HZ * (t + ph) / AUDIO_RATE)
                    )
                    self._dial_phase = (ph + frames) % AUDIO_RATE
                    out = samp.astype(np.int16)
                # sinon silence (attente prebuffer)
            outdata[:] = out.tobytes()

        self._stream = sd.RawOutputStream(
            samplerate=AUDIO_RATE,
            channels=1,
            dtype="int16",
            blocksize=BLOCK,
            device=self.device,
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def push_pcm(self, data: bytes) -> None:
        if not data:
            return
        with self._lock:
            self._remote_seen = True
            self._dial_active = False
            self._buf.extend(data)
            if len(self._buf) > self._max_buf_bytes:
                drop = len(self._buf) - self._max_buf_bytes
                del self._buf[:drop]
            if not self._primed and len(self._buf) >= self._prebuffer_bytes:
                self._primed = True

    def start_dial_tone(self) -> None:
        with self._lock:
            self._dial_active = True
            self._remote_seen = False
            self._primed = False
            self._dial_phase = 0.0
            self._buf.clear()


class LocalCallRecorder:
    def __init__(self, call_id: int) -> None:
        self.call_id = call_id
        self.line_chunks: list[bytes] = []
        self.mic_chunks: list[bytes] = []
        self.active = False

    def start(self) -> None:
        self.active = True
        self.line_chunks.clear()
        self.mic_chunks.clear()

    def add_line(self, pcm: bytes) -> None:
        if self.active and pcm:
            self.line_chunks.append(pcm)

    def add_mic(self, pcm: bytes) -> None:
        if self.active and pcm:
            self.mic_chunks.append(pcm)

    def stop_and_save(self) -> Optional[Path]:
        self.active = False
        line = b"".join(self.line_chunks)
        mic = b"".join(self.mic_chunks)
        if not line and not mic:
            return None
        n = max(len(line) // 2, len(mic) // 2, 1)
        line_arr = np.zeros(n, dtype=np.int16)
        mic_arr = np.zeros(n, dtype=np.int16)
        if line:
            la = np.frombuffer(line, dtype=np.int16)
            line_arr[: min(n, la.size)] = la[:n]
        if mic:
            ma = np.frombuffer(mic, dtype=np.int16)
            mic_arr[: min(n, ma.size)] = ma[:n]
        stereo = np.column_stack((line_arr, mic_arr)).astype(np.int16)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = RECORDINGS_DIR / f"desktop_call_{self.call_id}_{ts}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(AUDIO_RATE)
            wf.writeframes(stereo.tobytes())
        return path


class AudioSession:
    """Pont WebSocket audio + micro (thread asyncio dédié)."""

    def __init__(
        self,
        ws_base: str,
        call_id: int,
        input_device: Optional[int],
        output_device: Optional[int],
        on_status: Callable[[str], None],
        local_recorder: Optional[LocalCallRecorder] = None,
        stats: Optional[LiveAudioStats] = None,
    ) -> None:
        self.ws_url = f"{ws_base}/ws/outgoing-call/{call_id}/audio"
        self.input_device = input_device
        self.output_device = output_device
        self.on_status = on_status
        self.local_recorder = local_recorder
        self.stats = stats or LiveAudioStats()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._playback: Optional[PlaybackEngine] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio_ws")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.stats.set_connected(False)
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        asyncio.run(self._async_main())

    async def _async_main(self) -> None:
        self._playback = PlaybackEngine(self.output_device)
        self._playback.start()
        self._playback.start_dial_tone()
        self.on_status("Tonalité de numérotation… connexion audio")

        in_stream = sd.RawInputStream(
            samplerate=AUDIO_RATE,
            channels=1,
            dtype="int16",
            blocksize=BLOCK,
            device=self.input_device,
        )

        for attempt in range(12):
            if self._stop.is_set():
                break
            try:
                async with websockets.connect(self.ws_url, max_size=2**20, open_timeout=8) as ws:
                    self.on_status("Audio WebSocket connecté")
                    self.stats.set_connected(True)
                    in_stream.start()

                    async def send_mic() -> None:
                        loop = asyncio.get_running_loop()
                        while not self._stop.is_set():
                            data, _ = await loop.run_in_executor(None, in_stream.read, BLOCK)
                            if data:
                                b = bytes(data)
                                self.stats.note_tx(b)
                                if self.local_recorder:
                                    self.local_recorder.add_mic(b)
                                try:
                                    await ws.send(b)
                                except Exception:
                                    break
                            await asyncio.sleep(0.001)

                    sender = asyncio.create_task(send_mic())
                    try:
                        async for msg in ws:
                            if self._stop.is_set():
                                break
                            if isinstance(msg, bytes) and msg:
                                self.stats.note_rx(msg)
                                if self.local_recorder:
                                    self.local_recorder.add_line(msg)
                                if self._playback:
                                    self._playback.push_pcm(msg)
                    finally:
                        sender.cancel()
                        try:
                            await sender
                        except asyncio.CancelledError:
                            pass
                        self.stats.set_connected(False)
                    return
            except Exception as exc:
                err = str(exc)
                self.stats.set_connected(False)
                if "4404" in err or "404" in err.lower():
                    self.on_status(f"Attente session appel ({attempt + 1}/12)…")
                    await asyncio.sleep(0.5)
                    continue
                self.on_status(f"Audio WS: {exc}")
                await asyncio.sleep(1.0)

        in_stream.stop()
        in_stream.close()
        if self._playback:
            self._playback.stop()
        self.stats.set_connected(False)


class VocalGuardPhoneApp:
    def __init__(self) -> None:
        self.api_base = DEFAULT_API
        self.ws_base = DEFAULT_WS
        self.client = httpx.Client(timeout=30.0)
        self.active_call_id: Optional[int] = None
        self.audio: Optional[AudioSession] = None
        self.local_recorder: Optional[LocalCallRecorder] = None
        self.live_stats = LiveAudioStats()
        self._meter_job: Optional[str] = None
        self._in_map: dict[str, int] = {}
        self._out_map: dict[str, int] = {}

        self.root = tk.Tk()
        self.root.title("VocalGuard Phone")
        self.root.geometry("560x820")
        self.root.minsize(520, 700)
        self._build_ui()
        self._refresh_devices()
        self._poll_calls()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, **pad)
        ttk.Label(top, text="Numéro").grid(row=0, column=0, sticky=tk.W)
        self.number_var = tk.StringVar()
        self.number_entry = ttk.Entry(top, textvariable=self.number_var, font=("Segoe UI", 14))
        self.number_entry.grid(row=0, column=1, sticky=tk.EW, padx=(6, 0))
        self.number_entry.bind("<Double-Button-1>", lambda _e: self._start_call())
        top.columnconfigure(1, weight=1)

        dev = ttk.LabelFrame(self.root, text="Périphériques audio")
        dev.pack(fill=tk.X, **pad)
        self.in_dev_var = tk.StringVar()
        self.out_dev_var = tk.StringVar()
        ttk.Label(dev, text="Micro").grid(row=0, column=0, sticky=tk.W)
        self.in_combo = ttk.Combobox(dev, textvariable=self.in_dev_var, state="readonly", width=46)
        self.in_combo.grid(row=0, column=1, sticky=tk.EW, padx=4, columnspan=2)
        ttk.Label(dev, text="Casque / HP").grid(row=1, column=0, sticky=tk.W)
        self.out_combo = ttk.Combobox(dev, textvariable=self.out_dev_var, state="readonly", width=46)
        self.out_combo.grid(row=1, column=1, sticky=tk.EW, padx=4, columnspan=2)

        test_row = ttk.Frame(dev)
        test_row.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(6, 2))
        ttk.Button(test_row, text="Actualiser liste", command=self._refresh_devices).pack(side=tk.LEFT, padx=2)
        ttk.Button(test_row, text="Casque BT", command=self._pick_headset).pack(side=tk.LEFT, padx=2)
        ttk.Button(test_row, text="Test casque", command=self._test_speaker).pack(side=tk.LEFT, padx=2)
        ttk.Button(test_row, text="Test micro", command=self._test_mic).pack(side=tk.LEFT, padx=2)
        ttk.Label(test_row, text="Niveau micro:").pack(side=tk.LEFT, padx=(12, 4))
        self.level_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(test_row, variable=self.level_var, maximum=1.0, length=120).pack(side=tk.LEFT)
        dev.columnconfigure(1, weight=1)

        actions = ttk.Frame(self.root)
        actions.pack(fill=tk.X, **pad)
        ttk.Button(actions, text="Appeler", command=self._start_call).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions, text="Raccrocher", command=self._hangup).pack(side=tk.LEFT, padx=2)
        self.status_var = tk.StringVar(value="Prêt — testez casque et micro avant d'appeler")
        ttk.Label(actions, textvariable=self.status_var, wraplength=360).pack(side=tk.LEFT, padx=8)

        meters = ttk.LabelFrame(self.root, text="Niveaux & débit (temps réel)")
        meters.pack(fill=tk.X, **pad)
        ttk.Label(meters, text="Ligne").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        self.line_level_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(meters, variable=self.line_level_var, maximum=1.0, length=220).grid(
            row=0, column=1, sticky=tk.EW, padx=4, pady=2
        )
        self.line_pct_var = tk.StringVar(value="0 %")
        ttk.Label(meters, textvariable=self.line_pct_var, width=6).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(meters, text="Micro").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        self.mic_level_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(meters, variable=self.mic_level_var, maximum=1.0, length=220).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=2
        )
        self.mic_pct_var = tk.StringVar(value="0 %")
        ttk.Label(meters, textvariable=self.mic_pct_var, width=6).grid(row=1, column=2, sticky=tk.W)

        self.bitrate_var = tk.StringVar(value="Débit : —  |  WS : déconnecté")
        ttk.Label(meters, textvariable=self.bitrate_var).grid(
            row=2, column=0, columnspan=3, sticky=tk.W, padx=4, pady=(4, 2)
        )
        meters.columnconfigure(1, weight=1)

        dtmf = ttk.LabelFrame(self.root, text="Clavier DTMF")
        dtmf.pack(fill=tk.X, **pad)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]
        for i, k in enumerate(keys):
            ttk.Button(dtmf, text=k, width=4, command=lambda d=k: self._dtmf(d)).grid(
                row=i // 3, column=i % 3, padx=2, pady=2
            )

        hist = ttk.LabelFrame(self.root, text="Historique (double-clic sur une ligne = rappeler)")
        hist.pack(fill=tk.BOTH, expand=True, **pad)
        cols = ("id", "numero", "statut", "duree", "audio")
        self.tree = ttk.Treeview(hist, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (40, 110, 70, 50, 160)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.tree.bind("<Double-1>", self._on_history_double_click)
        sb = ttk.Scrollbar(hist, orient=tk.VERTICAL, command=self.tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=sb.set)

        btns = ttk.Frame(self.root)
        btns.pack(fill=tk.X, **pad)
        ttk.Button(btns, text="Actualiser liste", command=self._load_calls).pack(side=tk.LEFT)
        ttk.Button(btns, text="Écouter enreg.", command=self._play_server_recording).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Dossier local", command=self._open_local_folder).pack(side=tk.LEFT)

        foot = ttk.Label(self.root, text=f"API {self.api_base}", font=("Segoe UI", 8))
        foot.pack(fill=tk.X, padx=8, pady=2)

    def _set_status(self, msg: str) -> None:
        self.root.after(0, lambda: self.status_var.set(msg))

    def _set_level(self, v: float) -> None:
        self.root.after(0, lambda: self.level_var.set(v))

    def _refresh_devices(self) -> None:
        in_names, out_names, self._in_map, self._out_map = AudioDeviceHelper.list_devices()
        self.in_combo["values"] = in_names
        self.out_combo["values"] = out_names
        def_in, def_out = AudioDeviceHelper.default_labels(self._in_map, self._out_map)
        if def_in:
            self.in_dev_var.set(def_in)
        elif in_names:
            self.in_combo.current(0)
        if def_out:
            self.out_dev_var.set(def_out)
        elif out_names:
            self.out_combo.current(0)
        self._set_status(f"Périph. Windows par défaut : micro={def_in or '?'} | casque={def_out or '?'}")

    def _pick_headset(self) -> None:
        hin, hout = AudioDeviceHelper.find_headset_labels(self._in_map, self._out_map)
        if hin:
            self.in_dev_var.set(hin)
        if hout:
            self.out_dev_var.set(hout)
        if hin or hout:
            self._set_status(f"Casque BT sélectionné : {hout or hin}")
        else:
            messagebox.showinfo("Casque", "Aucun casque Bluetooth détecté dans la liste.")

    def _selected_devices(self) -> tuple[Optional[int], Optional[int]]:
        return self._in_map.get(self.in_dev_var.get()), self._out_map.get(self.out_dev_var.get())

    def _test_speaker(self) -> None:
        _, out_dev = self._selected_devices()
        AudioDeviceHelper.play_test_speaker(out_dev, self._set_status)

    def _test_mic(self) -> None:
        in_dev, out_dev = self._selected_devices()
        AudioDeviceHelper.test_microphone(in_dev, out_dev, self._set_level, self._set_status)

    def _load_calls(self) -> None:
        try:
            r = self.client.get(f"{self.api_base}/calls", params={"limit": 100})
            r.raise_for_status()
            calls = r.json().get("calls") or []
        except Exception as exc:
            self._set_status(f"Liste appels: {exc}")
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        for c in calls:
            self.tree.insert(
                "",
                tk.END,
                iid=str(c["id"]),
                values=(
                    c.get("id"),
                    c.get("phone_number") or "—",
                    c.get("status") or "—",
                    c.get("duration") or "—",
                    c.get("audio_file") or "—",
                ),
            )

    def _poll_calls(self) -> None:
        self._load_calls()
        self.root.after(15000, self._poll_calls)

    def _on_history_double_click(self, event: tk.Event) -> None:
        """Double-clic sur l'historique : remplit le numéro et lance l'appel."""
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        values = self.tree.item(row_id, "values")
        if len(values) < 2:
            return
        phone = str(values[1]).strip()
        if not phone or phone == "—":
            messagebox.showinfo("Rappel", "Aucun numéro pour cet appel.")
            return
        self.number_var.set(phone)
        self._start_call()

    def _start_call(self) -> None:
        number = self.number_var.get().strip()
        if not number:
            messagebox.showwarning("Numéro", "Saisissez un numéro.")
            return
        if self.active_call_id:
            messagebox.showinfo("Appel", "Un appel est déjà en cours.")
            return
        in_dev, out_dev = self._selected_devices()
        if in_dev is None or out_dev is None:
            messagebox.showwarning("Audio", "Choisissez micro et casque, puis Test casque / Test micro.")
            return
        try:
            r = self.client.post(f"{self.api_base}/calls/outgoing/start", json={"phone_number": number})
            r.raise_for_status()
            call_id = int(r.json()["call_id"])
        except Exception as exc:
            messagebox.showerror("Appel", str(exc))
            return
        self.active_call_id = call_id
        self.local_recorder = LocalCallRecorder(call_id)
        self.local_recorder.start()
        self.live_stats = LiveAudioStats()
        self.audio = AudioSession(
            self.ws_base,
            call_id,
            in_dev,
            out_dev,
            self._set_status,
            self.local_recorder,
            self.live_stats,
        )
        self.audio.start()
        self._start_meter_updates()
        self._set_status(f"Appel #{call_id} → {number} (tonalité puis ligne)")

    def _start_meter_updates(self) -> None:
        self._stop_meter_updates()
        self._update_meters()

    def _stop_meter_updates(self) -> None:
        if self._meter_job is not None:
            try:
                self.root.after_cancel(self._meter_job)
            except Exception:
                pass
            self._meter_job = None

    def _update_meters(self) -> None:
        snap = self.live_stats.snapshot()
        line = float(snap["line"])
        mic = float(snap["mic"])
        self.line_level_var.set(line)
        self.mic_level_var.set(mic)
        self.line_pct_var.set(f"{int(line * 100)} %")
        self.mic_pct_var.set(f"{int(mic * 100)} %")
        ws_state = "connecté" if snap["connected"] else "déconnecté"
        self.bitrate_var.set(
            f"Débit ↓ {snap['rx_kbps']:.1f} kbit/s  |  ↑ {snap['tx_kbps']:.1f} kbit/s  |  "
            f"total ↓ {snap['rx_total'] // 1024} Ko / ↑ {snap['tx_total'] // 1024} Ko  |  WS : {ws_state}"
        )
        if self.active_call_id is not None:
            self._meter_job = self.root.after(250, self._update_meters)
        else:
            self.line_level_var.set(0.0)
            self.mic_level_var.set(0.0)
            self.line_pct_var.set("0 %")
            self.mic_pct_var.set("0 %")
            self.bitrate_var.set("Débit : —  |  WS : déconnecté")
            self._meter_job = None

    def _hangup(self) -> None:
        if not self.active_call_id:
            return
        cid = self.active_call_id
        local_path: Optional[Path] = None
        try:
            if self.local_recorder:
                local_path = self.local_recorder.stop_and_save()
                self.local_recorder = None
            if self.audio:
                self.audio.stop()
                self.audio = None
            self.client.post(f"{self.api_base}/calls/outgoing/{cid}/hangup")
        except Exception as exc:
            self._set_status(f"Raccrocher: {exc}")
        finally:
            self.active_call_id = None
            self._stop_meter_updates()
            self.line_level_var.set(0.0)
            self.mic_level_var.set(0.0)
            self.line_pct_var.set("0 %")
            self.mic_pct_var.set("0 %")
            self.bitrate_var.set("Débit : —  |  WS : déconnecté")
            self._load_calls()
            server_path = self._download_server_recording(cid)
            msg_parts = [f"Appel #{cid} terminé."]
            if local_path:
                msg_parts.append(f"Local : {local_path}")
            else:
                msg_parts.append("Local : aucun flux audio capturé (vérifiez micro/casque).")
            if server_path:
                msg_parts.append(f"Serveur : {server_path}")
            else:
                msg_parts.append("Serveur : enregistrement en cours de finalisation — réessayez « Écouter enreg. » dans 5 s.")
            self.root.after(800, lambda: messagebox.showinfo("Fin d'appel", "\n".join(msg_parts)))

    def _download_server_recording(self, call_id: int, retries: int = 4) -> Optional[Path]:
        dest = RECORDINGS_DIR / f"server_call_{call_id}.wav"
        for attempt in range(retries):
            try:
                time.sleep(1.5 if attempt else 0.8)
                with urlopen(f"{self.api_base}/calls/{call_id}/recording", timeout=60) as resp:
                    data = resp.read()
                if len(data) > 1000:
                    dest.write_bytes(data)
                    return dest
            except Exception:
                continue
        return None

    def _dtmf(self, digit: str) -> None:
        if not self.active_call_id:
            return
        try:
            self.client.post(
                f"{self.api_base}/calls/outgoing/{self.active_call_id}/dtmf",
                json={"digit": digit},
            )
        except Exception as exc:
            self._set_status(f"DTMF: {exc}")

    def _play_server_recording(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Enregistrement", "Sélectionnez un appel.")
            return
        call_id = sel[0]
        url = f"{self.api_base}/calls/{call_id}/recording"
        local = RECORDINGS_DIR / f"server_call_{call_id}.wav"
        try:
            with urlopen(url, timeout=60) as resp:
                local.write_bytes(resp.read())
            os.startfile(str(local))
        except Exception as exc:
            messagebox.showerror("Enregistrement", f"Indisponible:\n{exc}")

    def _open_local_folder(self) -> None:
        os.startfile(str(RECORDINGS_DIR))

    def _on_close(self) -> None:
        if self.active_call_id:
            self._hangup()
        self._stop_meter_updates()
        self.client.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    VocalGuardPhoneApp().run()


if __name__ == "__main__":
    main()
