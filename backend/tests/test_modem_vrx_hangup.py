"""
Tests detection raccrochage VRX (faux positifs PCM vs vrais marqueurs DLE).
"""

from __future__ import annotations

import math

from backend.core.modem_handler import (
    _VrxDisconnectToneScanner,
    _VrxHangupScanner,
    _scan_hangup_tone_trim,
    _trim_pcm_tail,
    _vrx_buffer_has_hangup_marker,
    _vrx_dle_control_has_hangup_marker,
)


def test_dle_s_silence_is_not_hangup():
    """DLE-s = silence modem, pas un raccrochage (sinon messages coupes a 4s)."""
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, 0x73, 0x80, 0x90])) is False
    assert scanner.feed(bytes([0x10, ord("s")])) is False
    assert _vrx_dle_control_has_hangup_marker(bytes([0x10, ord("s")])) is False


def test_dle_h_is_hangup():
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, ord("h")])) is True


def test_pcm_without_dle_bytes_is_safe():
    scanner = _VrxHangupScanner()
    data = bytes(range(32, 200)) * 20
    assert scanner.feed(data) is False


def test_pcm_escaped_dle_is_ignored():
    """DLE-DLE dans le flux = octet PCM 0x10, pas un code controle."""
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, 0x10, 0x73])) is False


def test_no_carrier_text_detected():
    scanner = _VrxHangupScanner()
    assert scanner.feed(b"\r\nNO CARRIER\r\n") is True


def test_legacy_buffer_helper_still_works_on_control_tail():
    assert _vrx_dle_control_has_hangup_marker(bytes([0x10, ord("h")])) is True
    assert _vrx_buffer_has_hangup_marker(b"NO CARRIER") is True


def _quiet_u8(samples: int) -> bytes:
    return bytes([128] * samples)


def _tone440_u8(samples: int, *, amp: int = 40, rate: int = 8000, phase: float = 0.0) -> bytes:
    """Bip occupation FR (sinusoide 440 Hz en PCM u8)."""
    out = bytearray()
    for i in range(samples):
        val = int(amp * math.sin(2 * math.pi * 440.0 * i / rate + phase))
        out.append(max(0, min(255, 128 + val)))
    return bytes(out)


def _busy_train_u8(cycles: int = 3) -> bytes:
    """Suite continue occupation FR (phase preservee entre cycles)."""
    rate = 8000
    parts = bytearray(_quiet_u8(3200))
    phase = 0.0
    for _ in range(cycles):
        on = 4000
        parts.extend(_tone440_u8(on, phase=phase))
        phase += 2 * math.pi * 440.0 * on / rate
        parts.extend(_quiet_u8(4000))
    return bytes(parts)


def _noise_speech_u8(samples: int) -> bytes:
    """Pseudo-parole irreguliere (pas une sinusoide 440)."""
    out = bytearray()
    for i in range(samples):
        # Melange de basses frequences + impulsions.
        val = int(50 * math.sin(2 * math.pi * 180.0 * i / 8000.0))
        val += int(30 * math.sin(2 * math.pi * 720.0 * i / 8000.0 + 0.3))
        if i % 37 < 3:
            val += 60
        out.append(max(0, min(255, 128 + val)))
    return bytes(out)


def test_disconnect_tone_scanner_detects_french_busy_440():
    """Occupation FR 440 Hz ~0,5 s on / 0,5 s off."""
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    assert scanner.feed(_quiet_u8(3200), sample_width=1) is False
    for _ in range(2):
        assert scanner.feed(_tone440_u8(4000), sample_width=1) is False
        assert scanner.feed(_quiet_u8(4000), sample_width=1) is False
    assert scanner.feed(_tone440_u8(4000), sample_width=1) is False
    assert scanner.feed(_quiet_u8(800), sample_width=1) is True
    assert scanner.heard_speech is False
    assert scanner.trim_sec > 1.5


def test_disconnect_tone_scanner_detects_continuous_440():
    """Note continue 440 Hz (ligne morte / invitation a composer) = hangup."""
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    # ~0.9 s de 440 Hz sans silence : l'ancien scanner resettait apres 0.75 s.
    hit = scanner.feed(_tone440_u8(7200), sample_width=1)
    assert hit is True
    assert scanner.trim_sec >= 0.8


def test_disconnect_tone_scanner_ignores_speech():
    """La parole (pas 440 Hz stable) ne doit pas declencher la coupe."""
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    scanner.feed(_quiet_u8(4000), sample_width=1)
    for _ in range(4):
        assert scanner.feed(_noise_speech_u8(4000), sample_width=1) is False
        assert scanner.feed(_quiet_u8(800), sample_width=1) is False
    assert scanner.feed(_noise_speech_u8(8000), sample_width=1) is False


def test_disconnect_tone_scanner_speech_then_busy():
    """Apres un message, la tonalite 440 coupe bien."""
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    scanner.feed(_quiet_u8(1600), sample_width=1)
    scanner.feed(_noise_speech_u8(8000), sample_width=1)
    scanner.feed(_quiet_u8(4000), sample_width=1)
    for _ in range(2):
        assert scanner.feed(_tone440_u8(4000), sample_width=1) is False
        assert scanner.feed(_quiet_u8(4000), sample_width=1) is False
    assert scanner.feed(_tone440_u8(4000), sample_width=1) is False
    assert scanner.feed(_quiet_u8(800), sample_width=1) is True
    assert scanner.heard_speech is True


def test_disconnect_tone_scanner_works_on_large_serial_chunks():
    """Les lectures VRX ~0.5 s ne doivent plus masquer la tonalite FR."""
    blob = _busy_train_u8(3)
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    hit = False
    for i in range(0, len(blob), 4096):
        if scanner.feed(blob[i : i + 4096], sample_width=1):
            hit = True
            break
    assert hit is True
    assert scanner.heard_speech is False


def test_disconnect_tone_beeps_only_not_speech_flag_from_tone():
    """Tonalite seule : heard_speech reste False."""
    scanner = _VrxDisconnectToneScanner(threshold=28, sample_rate=8000)
    scanner.feed(_quiet_u8(3200), sample_width=1)
    for _ in range(2):
        scanner.feed(_tone440_u8(4000), sample_width=1)
        scanner.feed(_quiet_u8(4000), sample_width=1)
    scanner.feed(_tone440_u8(4000), sample_width=1)
    scanner.feed(_quiet_u8(800), sample_width=1)
    assert scanner.heard_speech is False


def test_trim_pcm_tail_removes_hangup_beeps():
    """La queue des bips est retiree, le debut du message reste."""
    speech = _quiet_u8(8000)
    beeps = _tone440_u8(2400)
    out = _trim_pcm_tail(speech + beeps, sample_width=1, sample_rate=8000, trim_sec=0.3)
    assert len(out) == 8000
    assert out == speech


def test_scan_hangup_tone_trim_finds_tail():
    """Post-traitement : coupe la queue 440 Hz d'un message+tonalite."""
    speech = _noise_speech_u8(8000) + _quiet_u8(4000)
    tone = _tone440_u8(4000)
    quiet = _quiet_u8(4000)
    data = speech + tone + quiet + tone + quiet + tone + quiet
    trim = _scan_hangup_tone_trim(data, sample_width=1, sample_rate=8000, threshold=28)
    assert trim > 2.0
    trimmed = _trim_pcm_tail(data, sample_width=1, sample_rate=8000, trim_sec=trim)
    assert len(trimmed) < len(data)
    assert len(trimmed) >= 8000


def test_vtx_hangup_blob_detects_dle_h_and_ignores_ring():
    from backend.core.modem_handler import ModemHandler

    modem = ModemHandler()
    try:
        assert modem._blob_means_vtx_hangup(b"\r\nRING\r\n") is False
        assert modem._playback_interrupted is False
        assert modem._blob_means_vtx_hangup(bytes([0x10, ord("h")])) is True
        assert modem._playback_interrupted is True
    finally:
        modem._modem_sync_executor.shutdown(wait=False)
