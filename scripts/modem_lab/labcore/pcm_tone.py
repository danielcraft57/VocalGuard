#!/usr/bin/env python3
"""Génération de signaux PCM u8 8 kHz (tests, calibration haut-parleur)."""

from __future__ import annotations

import math


def sine_u8(
    *,
    duration_sec: float,
    sample_rate: int = 8000,
    freq_hz: float = 440.0,
    amplitude: float = 100.0,
) -> bytes:
    """
    Sinusoïde centrée sur 128 ; ``amplitude`` = demi-crête en unités u8 (typ. < 128).
    """
    n = max(0, int(duration_sec * sample_rate))
    out = bytearray(n)
    two_pi_f = 2.0 * math.pi * freq_hz / float(sample_rate)
    for i in range(n):
        s = 128.0 + amplitude * math.sin(two_pi_f * i)
        out[i] = max(0, min(255, int(round(s))))
    return bytes(out)


def silence_u8(duration_sec: float, sample_rate: int = 8000) -> bytes:
    """Bloc silence (128)."""
    n = max(0, int(duration_sec * sample_rate))
    return bytes([128]) * n
