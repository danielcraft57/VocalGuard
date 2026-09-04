"""
Tests TurnVad (silence fin de tour).
"""

import struct

from backend.voice.turn_vad import TurnVad, TurnVadConfig


def _pcm(rms_approx: float, samples: int = 320) -> bytes:
    """Genere un buffer s16le constant."""
    val = int(max(-32000, min(32000, rms_approx)))
    return struct.pack("<" + "h" * samples, *([val] * samples))


def test_no_silence_before_speech():
    """Silence initial ne termine pas le tour."""
    vad = TurnVad(TurnVadConfig(speech_rms_threshold=300, turn_silence_ms=400))
    assert vad.feed(_pcm(0), frame_ms=20) is False
    assert vad.feed(_pcm(0), frame_ms=20) is False
    assert vad.ended is False


def test_turn_ends_after_speech_then_silence():
    """Parole puis silence → fin de tour."""
    vad = TurnVad(TurnVadConfig(speech_rms_threshold=300, turn_silence_ms=100))
    assert vad.feed(_pcm(2000), frame_ms=20) is False
    assert vad.heard_speech is True
    # 100 ms silence
    assert vad.feed(_pcm(0), frame_ms=50) is False
    assert vad.feed(_pcm(0), frame_ms=50) is True
    assert vad.ended is True


def test_feed_buffer_detects_end():
    """Decoupe buffer OK."""
    vad = TurnVad(TurnVadConfig(speech_rms_threshold=300, turn_silence_ms=40))
    speech = _pcm(5000, samples=320)
    silence = _pcm(0, samples=320 * 4)
    assert vad.feed_buffer(speech + silence, sample_rate=16000, frame_ms=20) is True
