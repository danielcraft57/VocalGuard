"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilité modem voix (callattendant, VocalGuard).
Lecture et conversion pour STT (16 kHz 16-bit).
"""

import math
import re
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydub import AudioSegment


def write_beep_wav_8k(out_path: Path, *, freq_hz: int = 1000, duration_ms: int = 280) -> None:
    """
    Genere un bip unique court (8 kHz, mono, 8-bit), style repondeur classique.

    @param out_path Fichier WAV de sortie.
    @param freq_hz Frequence du bip en hertz.
    @param duration_ms Duree du bip en millisecondes.
    """
    rate = 8000
    sample_count = max(1, int(rate * duration_ms / 1000))
    samples = bytearray(sample_count)
    amplitude = 100
    fade = max(1, int(rate * 0.01))  # 10 ms fade in/out anti-clic
    for i in range(sample_count):
        t = i / rate
        env = 1.0
        if i < fade:
            env = i / fade
        elif i > sample_count - fade:
            env = (sample_count - i) / fade
        wave_val = math.sin(2.0 * math.pi * freq_hz * t) * env
        value = 128 + int(amplitude * wave_val)
        samples[i] = max(0, min(255, value))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(bytes(samples))


def pcm_u8_chunk_peak(raw: bytes) -> int:
    """
    Pic d'amplitude d'un bloc PCM 8-bit centré sur 128 (0 = silence).

    @param raw Octets audio bruts du flux VRX.
    @returns Écart maximal par rapport au silence (0-127).
    """
    if not raw:
        return 0
    peak = 0
    for byte in raw:
        deviation = abs(byte - 128)
        if deviation > peak:
            peak = deviation
    return peak


def trim_leading_trailing_silence(
    segment: "AudioSegment",
    *,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    padding_ms: int = 30,
) -> "AudioSegment":
    """
    Retire le silence au debut et a la fin (compatible pydub sans strip_silence).
    """
    from pydub.silence import detect_leading_silence

    if len(segment) <= 0:
        return segment
    start = detect_leading_silence(
        segment, silence_threshold=silence_threshold, chunk_size=chunk_size
    )
    end = detect_leading_silence(
        segment.reverse(), silence_threshold=silence_threshold, chunk_size=chunk_size
    )
    start = max(0, start - padding_ms)
    end = max(0, end - padding_ms)
    duration = len(segment)
    if start + end >= duration:
        return segment
    return segment[start : duration - end]


def export_wav_8k_8bit(segment: "AudioSegment", out_path: Path, *, normalize: bool = False) -> None:
    """
    Exporte un AudioSegment en WAV 8 kHz, mono, 8-bit non signé.
    Format attendu par le modem Conexant (mode voix série) et IVR téléphone.

    Args:
        segment: Segment pydub (peut être 16-bit, autre rate).
        out_path: Fichier WAV de sortie.
        normalize: Normalise le niveau (~ -3 dBFS) avant conversion 8-bit.
    """
    segment = segment.set_channels(1).set_frame_rate(8000)
    if normalize:
        peak = segment.max or 0
        if peak > 0:
            # Cible ~28000 sur 32767 (-3 dB) pour limiter la distorsion 8-bit.
            target = 28000.0
            gain_db = 20.0 * math.log10(target / float(peak))
            if abs(gain_db) > 0.05:
                segment = segment.apply_gain(gain_db)
    raw = segment.raw_data
    samples_8 = bytearray()
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = int(round((s16 / 32768.0) * 127.0 + 128.0))
        samples_8.append(max(0, min(255, u8)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(bytes(samples_8))


def load_wav_as_16k16bit_pcm(wav_path: Path) -> bytes:
    """
    Charge un fichier WAV (8 kHz 8-bit ou 16 kHz 16-bit) et retourne des bytes
    PCM 16-bit mono 16 kHz pour la reconnaissance vocale (VOSK/Whisper).

    Args:
        wav_path: Chemin vers le fichier WAV.

    Returns:
        Données PCM 16-bit little-endian, 16 kHz, mono.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("pydub requis: pip install pydub")

    segment = AudioSegment.from_file(str(wav_path))
    segment = segment.set_frame_rate(16000).set_channels(1)
    return segment.raw_data


def has_alsa_capture_devices() -> bool:
    """
    True si `arecord -l` liste au moins un peripherique de capture (carte son / modem ALSA).
    Sur Pi + USR5637 sans carte capture, la section CAPTURE est vide : preferer VRX serie.
    """
    try:
        r = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = r.stdout or ""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    in_capture_section = False
    for line in out.splitlines():
        if "CAPTURE" in line.upper() and "HARDWARE" in line.upper():
            in_capture_section = True
            continue
        if in_capture_section and re.match(r"^\s*card\s+\d+:", line, re.I):
            return True
    return False


def pcm_u8_8k_to_s16le_16k(data: bytes) -> bytes:
    """PCM modem 8 kHz 8-bit unsigned -> PCM 16 kHz 16-bit LE (duplication d echantillon, 8k->16k)."""
    out = bytearray()
    for b in data:
        s = int(b) - 128
        s16 = max(-32768, min(32767, s * 256))
        packed = s16.to_bytes(2, "little", signed=True)
        out.extend(packed)
        out.extend(packed)
    return bytes(out)


def pcm_s16le_16k_mono_to_u8_8k(data: bytes) -> bytes:
    """Sous-echantillonne 16 kHz s16le mono vers 8 kHz 8-bit unsigned (1 echantillon sur 2)."""
    out = bytearray()
    for i in range(0, len(data) - 1, 4):
        s16 = int.from_bytes(data[i : i + 2], "little", signed=True)
        u8 = max(0, min(255, (s16 >> 8) + 128))
        out.append(u8)
    return bytes(out)


def pcm_s16le_rms(data: bytes) -> float:
    """
    RMS d'un buffer PCM s16le mono (valeur 0..32767 environ).

    Utilise pour VAD : ne pas ouvrir VTX sur du silence (evite de saccader l'ecoute ligne).
    """
    if not data or len(data) < 2:
        return 0.0
    n = len(data) // 2
    if n <= 0:
        return 0.0
    acc = 0.0
    for i in range(0, n * 2, 2):
        s = int.from_bytes(data[i : i + 2], "little", signed=True)
        acc += float(s) * float(s)
    return (acc / float(n)) ** 0.5


def write_stereo_u8_8k_wav(path: Path, line_track: bytes, mic_track: bytes) -> None:
    """
    WAV stéréo 8 kHz 8-bit : canal gauche = ligne (VRX), canal droit = micro (VTX).
    Piste la plus courte est complétée par silence (128).
    """
    n = max(len(line_track), len(mic_track))
    if n == 0:
        return
    silence = 128
    line = line_track.ljust(n, bytes([silence]))
    mic = mic_track.ljust(n, bytes([silence]))
    stereo = bytearray(n * 2)
    for i in range(n):
        stereo[i * 2] = line[i]
        stereo[i * 2 + 1] = mic[i]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(bytes(stereo))
