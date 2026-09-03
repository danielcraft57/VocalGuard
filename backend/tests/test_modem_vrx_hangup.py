"""
Tests detection raccrochage VRX (faux positifs PCM vs vrais marqueurs DLE).
"""

from backend.core.modem_handler import (
    _VrxDisconnectToneScanner,
    _VrxHangupScanner,
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


def _beep_u8(samples: int) -> bytes:
    """Bloc PCM u8 avec pic fort type bip tonalite."""
    return bytes([128 + 90 if i % 8 < 4 else 128 for i in range(samples)])


def _quiet_u8(samples: int) -> bytes:
    return bytes([128] * samples)


def test_disconnect_tone_scanner_detects_four_short_beeps_after_silence():
    scanner = _VrxDisconnectToneScanner(threshold=60, min_beeps=4, sample_rate=8000)
    assert scanner.feed(_quiet_u8(4000), sample_width=1) is False
    for _ in range(3):
        assert scanner.feed(_beep_u8(800), sample_width=1) is False
        assert scanner.feed(_quiet_u8(1600), sample_width=1) is False
    assert scanner.feed(_beep_u8(800), sample_width=1) is False
    assert scanner.feed(_quiet_u8(800), sample_width=1) is True


def test_disconnect_tone_scanner_ignores_speech_syllables():
    """La parole (sons longs) ne doit pas compter comme 4 bips."""
    scanner = _VrxDisconnectToneScanner(threshold=60, min_beeps=4, sample_rate=8000)
    scanner.feed(_quiet_u8(4000), sample_width=1)
    for _ in range(6):
        assert scanner.feed(_beep_u8(4000), sample_width=1) is False
        assert scanner.feed(_quiet_u8(400), sample_width=1) is False


def test_disconnect_tone_scanner_ignores_quiet_stream():
    scanner = _VrxDisconnectToneScanner(threshold=60, min_beeps=4, sample_rate=8000)
    assert scanner.feed(_quiet_u8(8000), sample_width=1) is False


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
