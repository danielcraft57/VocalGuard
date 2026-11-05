"""
Utilitaires audio bureau (micro, casque) sans dependance Tk.
"""

from __future__ import annotations

import math
import os
import wave
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

import numpy as np
import sounddevice as sd

AUDIO_RATE = 16000
# WAV modem (11 kHz / 8 kHz) normalises fort : bureau plus doux et un peu plus lent.
STUDIO_PLAY_GAIN = float(os.environ.get("VG_STUDIO_PLAY_GAIN", "0.35"))
STUDIO_PLAY_SPEED = float(os.environ.get("VG_STUDIO_PLAY_SPEED", "0.90"))
STUDIO_OUTPUT_RATE = int(os.environ.get("VG_STUDIO_OUTPUT_RATE", "44100"))
STUDIO_MIC_GAIN = float(os.environ.get("VG_STUDIO_MIC_GAIN", "1.0"))


def read_studio_float(name: str, default: float) -> float:
    """
    Lit un reglage numerique depuis l'environnement (studio.env).

    @param name Cle ex. VG_STUDIO_MIC_GAIN.
    @param default Valeur si absente ou invalide.
    @returns Float borne raisonnablement.
    """
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def normalize_device_index(device: Optional[int], *, kind: str) -> Optional[int]:
    """
    Verifie qu'un index PortAudio est utilisable pour entree ou sortie.

    @param device Index ou None (defaut systeme).
    @param kind ``input`` ou ``output``.
    @returns Index valide ou None.
    """
    key_in = "max_input_channels"
    key_out = "max_output_channels"
    try:
        if device is None:
            defaults = sd.default.device
            if kind == "input":
                device = defaults[0] if isinstance(defaults, (tuple, list)) else defaults
            else:
                device = defaults[1] if isinstance(defaults, (tuple, list)) else defaults
        idx = int(device)
        info = sd.query_devices(idx)
        if kind == "input":
            if int(info.get(key_in) or 0) < 1:
                return None
        elif int(info.get(key_out) or 0) < 1:
            return None
        return idx
    except Exception:
        return None


def input_device_candidates(preferred: Optional[int]) -> List[Optional[int]]:
    """
    Ordre de tentative micro : choix UI, defaut Windows, auto.

    @param preferred Index combo utilisateur.
    @returns Liste d'index a essayer.
    """
    seen: set[Optional[int]] = set()
    order: List[Optional[int]] = []

    def _add(dev: Optional[int]) -> None:
        if dev in seen:
            return
        norm = normalize_device_index(dev, kind="input")
        if norm is not None:
            seen.add(norm)
            order.append(norm)
        elif dev is None and None not in seen:
            seen.add(None)
            order.append(None)

    _add(preferred)
    try:
        _add(sd.default.device[0])
    except Exception:
        pass
    _add(None)
    return order or [None]


def output_device_candidates(preferred: Optional[int]) -> List[Optional[int]]:
    """
    Ordre de tentative sortie audio.

    @param preferred Index combo utilisateur.
    @returns Liste d'index a essayer.
    """
    seen: set[Optional[int]] = set()
    order: List[Optional[int]] = []

    def _add(dev: Optional[int]) -> None:
        if dev in seen:
            return
        norm = normalize_device_index(dev, kind="output")
        if norm is not None:
            seen.add(norm)
            order.append(norm)
        elif dev is None and None not in seen:
            seen.add(None)
            order.append(None)

    _add(preferred)
    try:
        _add(sd.default.device[1])
    except Exception:
        pass
    _add(None)
    return order or [None]


def pcm16_from_f32(arr: np.ndarray) -> bytes:
    """
    Convertit un buffer float32 mono en PCM 16 bits.

    @param arr Echantillons [-1, 1].
    @returns Octets PCM little-endian.
    """
    clipped = np.clip(arr, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


def _resample_linear(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """
    Reechantillonnage simple pour lecture bureau (WAV modem 11 kHz -> 44.1 kHz).

    @param audio Mono float32.
    @param orig_rate Hz source.
    @param target_rate Hz cible.
    @returns Buffer resample.
    """
    if orig_rate <= 0 or target_rate <= 0 or orig_rate == target_rate or len(audio) < 2:
        return audio
    duration = len(audio) / float(orig_rate)
    n_out = max(2, int(round(duration * target_rate)))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def read_wav_mono_f32(path: Union[str, Path]) -> Tuple[np.ndarray, int]:
    """
    Decode un WAV mono/stereo en float32 [-1, 1] (8-bit modem ou 16-bit).

    @param path Fichier WAV local.
    @returns (echantillons mono, sample_rate Hz).
    @raises ValueError Format non supporte.
    """
    with wave.open(str(path), "rb") as wf:
        rate = int(wf.getframerate())
        channels = int(wf.getnchannels())
        width = int(wf.getsampwidth())
        frames = wf.readframes(wf.getnframes())

    if width == 1:
        raw = np.frombuffer(frames, dtype=np.uint8)
        audio = (raw.astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
    elif width == 3:
        padded = frames + b"\x00" * ((4 - len(frames) % 4) % 4)
        raw = np.frombuffer(padded, dtype=np.uint8).reshape(-1, 4)
        vals = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        vals = np.where(vals >= 8388608, vals - 16777216, vals)
        audio = vals.astype(np.float32) / 8388608.0
    elif width == 4:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483647.0
    else:
        raise ValueError(f"WAV sampwidth {width} non supporte")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return np.clip(audio, -1.0, 1.0), rate


def prepare_studio_playback(
    audio: np.ndarray,
    sample_rate: int,
    *,
    gain: Optional[float] = None,
    speed: Optional[float] = None,
    output_rate: Optional[int] = None,
) -> Tuple[np.ndarray, int]:
    """
    Adapte un WAV modem pour casque/HP bureau (volume + debit + resample).

    @param audio Mono float32.
    @param sample_rate Hz du fichier.
    @param gain Multiplicateur amplitude (defaut VG_STUDIO_PLAY_GAIN).
    @param speed < 1 ralentit (defaut VG_STUDIO_PLAY_SPEED).
    @param output_rate Reechantillonner avant lecture (defaut 44100, 0 = desactive).
    @returns (audio, samplerate a passer a sounddevice.play).
    """
    g = STUDIO_PLAY_GAIN if gain is None else float(gain)
    sp = STUDIO_PLAY_SPEED if speed is None else float(speed)
    out_hz = STUDIO_OUTPUT_RATE if output_rate is None else int(output_rate)
    sp = max(0.5, min(1.5, sp))
    g = max(0.05, min(2.0, g))

    out = np.clip(audio * g, -1.0, 1.0)
    rate = int(sample_rate)
    if out_hz > 0 and rate > 0 and rate != out_hz:
        out = _resample_linear(out, rate, out_hz)
        rate = out_hz
    play_rate = max(1000, int(round(rate * sp)))
    return out, play_rate


class AudioDeviceHelper:
    """Liste et selection des peripheriques sounddevice."""

    @staticmethod
    def list_devices() -> tuple[list[str], list[str], dict[str, int], dict[str, int]]:
        """
        @returns (labels_in, labels_out, map_in, map_out).
        """
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
        """Labels par defaut systeme."""
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
        """
        Casque Bluetooth : micro = Hands-Free, ecoute = Stereo / casque classique.

        @returns Labels combo entree / sortie.
        """
        in_label = out_label = None

        def _score_input(label: str) -> int:
            low = label.lower()
            if "hands-free" in low or "ag audio" in low or "mains-libres" in low:
                return 3
            if "headset" in low or "casque" in low:
                return 2
            if "microphone" in low or "micro" in low:
                return 1
            return 0

        def _score_output(label: str) -> int:
            low = label.lower()
            if "stereo" in low or "haut-parleur" in low or "speaker" in low:
                return 3
            if "headset" in low or "casque" in low:
                return 2
            return 1

        best_in = max(in_map.keys(), key=_score_input) if in_map else None
        if best_in and _score_input(best_in) > 0:
            in_label = best_in
        best_out = max(out_map.keys(), key=_score_output) if out_map else None
        if best_out and _score_output(best_out) > 0:
            out_label = best_out
        return in_label, out_label

    @staticmethod
    def play_test_speaker(
        device: Optional[int],
        on_done: Callable[[str], None],
        *,
        output_gain: float = 0.2,
    ) -> None:
        """
        Bip de test sur la sortie choisie.

        @param device Index sounddevice.
        @param on_done Callback message UI.
        @param output_gain Amplitude 0..1 (volume bureau).
        """

        def _run() -> None:
            last_err: Optional[Exception] = None
            amp = max(0.02, min(1.0, float(output_gain)))
            for dev in output_device_candidates(device):
                try:
                    t = np.arange(int(AUDIO_RATE * 0.25), dtype=np.float64) / AUDIO_RATE
                    tone = (amp * np.sin(2 * math.pi * 440.0 * t)).astype(np.float32)
                    sd.play(tone, AUDIO_RATE, device=dev)
                    sd.wait()
                    on_done("Test HP OK.")
                    return
                except Exception as exc:
                    last_err = exc
            on_done(f"Test HP : {last_err}")

        import threading

        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def probe_microphone(
        device: Optional[int],
        on_level: Callable[[float], None],
        on_done: Callable[[str], None],
        *,
        seconds: float = 2.5,
        mic_gain: float = 1.0,
    ) -> None:
        """
        Ecoute courte du micro pour regler le niveau (sans STT).

        @param device Index entree.
        @param on_level RMS normalise 0..1 pendant la capture.
        @param on_done Message final UI.
        @param seconds Duree du test.
        @param mic_gain Gain applique (meme reglage que le Studio).
        """

        def _run() -> None:
            peak = 0.0
            gain = max(0.1, min(3.0, float(mic_gain)))
            last_err: Optional[Exception] = None

            def _cb(indata, _frames, _time, status) -> None:  # noqa: ANN001
                nonlocal peak
                if status:
                    pass
                mono = indata[:, 0]
                rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))) * gain
                peak = max(peak, rms)
                on_level(min(1.0, rms * 8.0))

            for dev in input_device_candidates(device):
                peak = 0.0
                try:
                    with sd.InputStream(
                        samplerate=AUDIO_RATE,
                        channels=1,
                        dtype="float32",
                        device=dev,
                        callback=_cb,
                        blocksize=int(AUDIO_RATE * 0.05),
                    ):
                        sd.sleep(int(max(0.5, seconds) * 1000))
                    pct = int(min(100, peak * 100 * 8))
                    if pct < 3:
                        on_done(
                            "Micro tres faible — montez le gain micro ou parlez plus pres."
                        )
                    elif pct > 95:
                        on_done(
                            f"Micro saturé ({pct} %) — baissez le gain micro."
                        )
                    else:
                        on_done(f"Micro OK — niveau pic ~{pct} %.")
                    return
                except Exception as exc:
                    last_err = exc
            on_done(f"Test micro : {last_err}")

        import threading

        threading.Thread(target=_run, daemon=True).start()
