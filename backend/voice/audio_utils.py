"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilité modem voix (callattendant, VocalGuard).
Lecture et conversion pour STT (16 kHz 16-bit).
"""

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
