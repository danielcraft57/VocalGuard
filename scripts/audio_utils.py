"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilite modem voix (callattendant, VocalGuard).
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydub import AudioSegment


def export_wav_8k_8bit(segment: "AudioSegment", out_path: Path) -> None:
    """
    Exporte un AudioSegment en WAV 8 kHz, mono, 8-bit non signe.
    Format attendu par le modem Conexant (mode voix serie) et IVR telephone.

    Args:
        segment: Segment pydub (peut etre 16-bit, autre rate).
        out_path: Fichier WAV de sortie.
    """
    segment = segment.set_frame_rate(8000).set_channels(1)
    raw = segment.raw_data
    # 16-bit LE -> 8-bit unsigned (128 = silence)
    samples_8 = []
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = max(0, min(255, (s16 >> 8) + 128))
        samples_8.append(u8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import wave
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(bytes(samples_8))
