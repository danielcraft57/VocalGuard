"""
Tests AT+VTR (full-duplex) : silence PCM, sequences DLE, helpers.
"""

from __future__ import annotations

from backend.core.modem_handler import (
    _DTE_END_VOICE_TX_RX,
    _VOICE_TR,
    _escape_dle_pcm,
    modem_silence_pcm,
)
from backend.voice.modem_profile import (
    CONEXANT_VOICE_PROFILE,
    USR_FALLBACK_PROFILE,
    USR_VOICE_PROFILE,
)


def test_voice_tr_command_is_vtr():
    """La commande full-duplex doit etre AT+VTR."""
    assert _VOICE_TR == "AT+VTR"


def test_dle_caret_ends_vtr():
    """USR5637 : fin VTR = DLE ^ (0x10 0x5E)."""
    assert _DTE_END_VOICE_TX_RX == bytes([0x10, 0x5E])


def test_modem_silence_pcm_usr_s16():
    """Silence USR 16-bit = zeros, aligne sur sample_width."""
    pcm = modem_silence_pcm(USR_VOICE_PROFILE, 0.04)
    assert len(pcm) > 0
    assert len(pcm) % 2 == 0
    assert pcm == bytes(len(pcm))
    expected = int(USR_VOICE_PROFILE.bytes_per_sec * 0.04)
    expected -= expected % 2
    assert len(pcm) == expected


def test_modem_silence_pcm_u8():
    """Silence 8-bit = 0x80."""
    pcm = modem_silence_pcm(USR_FALLBACK_PROFILE, 0.04)
    assert len(pcm) > 0
    assert all(b == 0x80 for b in pcm)
    pcm_cx = modem_silence_pcm(CONEXANT_VOICE_PROFILE, 0.02)
    assert len(pcm_cx) > 0
    assert all(b == 0x80 for b in pcm_cx)


def test_escape_dle_in_silence_and_pcm():
    """Les DLE dans le PCM TX doivent etre doubles (V.253)."""
    raw = bytes([0x00, 0x10, 0x20, 0x10])
    assert _escape_dle_pcm(raw) == bytes([0x00, 0x10, 0x10, 0x20, 0x10, 0x10])
    assert _escape_dle_pcm(b"\x80\x80") == b"\x80\x80"
