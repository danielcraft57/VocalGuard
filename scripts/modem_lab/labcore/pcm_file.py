#!/usr/bin/env python3
"""Chargement PCM 8 kHz mono 8-bit depuis WAV — pour tests offline du VAD sans modem."""

from __future__ import annotations

import wave
from pathlib import Path


def read_wav_mono_u8(path: Path, *, max_bytes: int | None = None) -> tuple[bytes, int]:
    """
    Lit un WAV **mono**, 8 ou 16 bits ; renvoie PCM **unsigned 8-bit** + fréquence d'échantillonnage.

    Si la fréquence n'est pas 8000 Hz, l'appelant doit resampler ; cette fonction ne rééchantillonne pas.
    """
    with wave.open(str(path), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        fr = wf.getframerate()
        if nch != 1:
            raise ValueError(f"mono requis: {path.name} a {nch} canaux")
        if sw not in (1, 2):
            raise ValueError(f"8 ou 16 bits requis: {sw}")
        nframes = wf.getnframes()
        need = nframes if max_bytes is None else min(nframes, max(0, max_bytes))
        raw = wf.readframes(need)
    if sw == 1:
        pcm = bytes(raw)
    else:
        out = bytearray(len(raw) // 2)
        j = 0
        for i in range(0, len(raw), 2):
            sample = int.from_bytes(raw[i : i + 2], "little", signed=True)
            u = (sample + 32768) * 255 // 65535
            out[j] = max(0, min(255, u))
            j += 1
        pcm = bytes(out)
    return pcm, int(fr)


def assert_pcm_8k(pcm: bytes, rate: int) -> None:
    """Lève si le flux n'est pas utilisable tel quel par le VAD 8 kHz."""
    if rate != 8000:
        raise ValueError(f"8000 Hz requis pour le lab VAD, obtenu {rate}")
