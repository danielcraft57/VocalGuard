"""
Enregistrement WAV stereo (ligne gauche, micro droite) pendant un appel modem.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Optional


class DualMonoCallRecorder:
    """
    Ecrit un WAV 16 kHz s16le stereo : canal L = flux ligne (VRX), R = micro (montant).

    Les blocs sont alignes sur la taille micro (ex. 320 frames sounddevice) ; si le micro
    manque (silence PTT), on pad avec des zeros sur le canal droit.
    """

    _BLOCK = 640  # 320 echantillons * 2 octets (s16 mono)

    def __init__(self, path: Path) -> None:
        self._path = path
        self._wav: Optional[wave.Wave_write] = None
        self._line_buf = bytearray()
        self._mic_buf = bytearray()

    def open(self) -> None:
        """Cree le fichier et l'entete WAV."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        w = wave.open(str(self._path), "wb")
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(16000)
        self._wav = w

    def feed_line(self, pcm16_mono: bytes) -> None:
        """
        Ajoute du PCM ligne (modem vers casque).

        @param pcm16_mono Mono s16le 16 kHz.
        """
        if not pcm16_mono or self._wav is None:
            return
        self._line_buf.extend(pcm16_mono)
        self._flush()

    def feed_mic(self, pcm16_mono: bytes) -> None:
        """
        Ajoute du PCM micro (montant).

        @param pcm16_mono Mono s16le 16 kHz.
        """
        if not pcm16_mono or self._wav is None:
            return
        self._mic_buf.extend(pcm16_mono)
        self._flush()

    def _flush(self) -> None:
        if self._wav is None:
            return
        while len(self._line_buf) >= self._BLOCK:
            left = bytes(self._line_buf[: self._BLOCK])
            del self._line_buf[: self._BLOCK]
            if len(self._mic_buf) >= self._BLOCK:
                right = bytes(self._mic_buf[: self._BLOCK])
                del self._mic_buf[: self._BLOCK]
            else:
                right = b"\x00" * self._BLOCK
            stereo = self._interleave(left, right)
            self._wav.writeframes(stereo)
        # Micro sans ligne recente : ecrit quand meme (L silence, R micro)
        while len(self._mic_buf) >= self._BLOCK and len(self._line_buf) < self._BLOCK:
            right = bytes(self._mic_buf[: self._BLOCK])
            del self._mic_buf[: self._BLOCK]
            left = b"\x00" * self._BLOCK
            stereo = self._interleave(left, right)
            self._wav.writeframes(stereo)
        if len(self._mic_buf) > self._BLOCK * 64:
            del self._mic_buf[: len(self._mic_buf) - self._BLOCK * 32]

    @staticmethod
    def _interleave(left: bytes, right: bytes) -> bytes:
        """Entrelace deux buffers mono meme longueur."""
        out = bytearray(len(left) * 2)
        j = 0
        for i in range(0, len(left), 2):
            out[j] = left[i]
            out[j + 1] = left[i + 1]
            out[j + 2] = right[i]
            out[j + 3] = right[i + 1]
            j += 4
        return bytes(out)

    def close(self) -> None:
        """Ferme le WAV et ecrit les blocs partiels restants."""
        if self._wav is not None:
            try:
                self._flush_tail()
                self._wav.close()
            except Exception:
                pass
            self._wav = None
        self._line_buf.clear()
        self._mic_buf.clear()

    def _flush_tail(self) -> None:
        """Ecrit les echantillons restants (appels courts)."""
        if self._wav is None:
            return
        if not self._line_buf and not self._mic_buf:
            return
        max_len = max(len(self._line_buf), len(self._mic_buf))
        if max_len < 2:
            return
        if max_len % 2:
            max_len += 1
        left = bytes(self._line_buf).ljust(max_len, b"\x00")[:max_len]
        right = bytes(self._mic_buf).ljust(max_len, b"\x00")[:max_len]
        stereo = self._interleave(left, right)
        self._wav.writeframes(stereo)


def session_wav_path(
    base_dir: Path,
    session_id: int,
    *,
    phone_digits: Optional[str] = None,
) -> Path:
    """
    Chemin fichier pour une session.

    @param base_dir Dossier enregistrements.
    @param session_id Id call_session.
    @returns Chemin .wav.
    """
    from datetime import datetime

    base_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    phone = (phone_digits or "appel").strip().replace(" ", "")[:24] or "appel"
    return base_dir / f"{ts}_{phone}_s{session_id}.wav"
