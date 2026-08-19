"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilité modem voix (callattendant, VocalGuard).
Lecture et conversion pour STT (16 kHz 16-bit).
"""

import re
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydub import AudioSegment


def export_wav_8k_8bit(segment: "AudioSegment", out_path: Path) -> None:
    """
    Exporte un AudioSegment en WAV 8 kHz, mono, 8-bit non signé.
    Format attendu par le modem Conexant (mode voix série) et IVR téléphone.

    Args:
        segment: Segment pydub (peut être 16-bit, autre rate).
        out_path: Fichier WAV de sortie.
    """
    segment = segment.set_frame_rate(8000).set_channels(1)
    raw = segment.raw_data
    samples_8 = []
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = max(0, min(255, (s16 >> 8) + 128))
        samples_8.append(u8)
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
