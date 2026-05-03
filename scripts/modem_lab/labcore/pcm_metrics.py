#!/usr/bin/env python3
"""Métriques sur trames PCM 8-bit unsigned (centré sur 128), 8 kHz — même convention que le flux AT+VRX USR."""

from __future__ import annotations

import math
from typing import Generator


def frame_length_bytes(sample_rate: int, frame_ms: float) -> int:
    """Nombre d'octets par trame mono 8-bit pour une durée donnée."""
    n = int(round(sample_rate * max(frame_ms, 1.0) / 1000.0))
    return max(8, n)


def mean_abs_deviation_u8(frame: bytes) -> float:
    """
    Moyenne des |sample - 128| — insensible au décalage DC, robuste pour parole téléphonique.

    Aligné sur ``modem_handler._pcm_u8_mean_abs_deviation`` (seuil ~18 typique en lab).
    """
    if not frame:
        return 0.0
    acc = 0
    for b in frame:
        acc += abs(b - 128)
    return acc / float(len(frame))


def rms_u8_centered(frame: bytes) -> float:
    """RMS des échantillons centrés (b - 128) sur [-127,127]."""
    if not frame:
        return 0.0
    s = 0.0
    for b in frame:
        d = float(b) - 128.0
        s += d * d
    return math.sqrt(s / float(len(frame)))


def iter_complete_frames(
    buffer: bytearray,
    chunk: bytes,
    frame_len: int,
) -> Generator[bytes, None, None]:
    """
    Ajoute ``chunk`` au buffer, yield chaque trame complète de ``frame_len`` octets.

    Laisse les octets incomplets dans ``buffer``.
    """
    if frame_len <= 0:
        return
    buffer.extend(chunk)
    while len(buffer) >= frame_len:
        yield bytes(buffer[:frame_len])
        del buffer[:frame_len]

