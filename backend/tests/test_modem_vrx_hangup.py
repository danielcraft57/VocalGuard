"""
Tests detection raccrochage VRX (faux positifs PCM vs vrais marqueurs DLE).
"""

from backend.core.modem_handler import (
    _VrxHangupScanner,
    _vrx_buffer_has_hangup_marker,
    _vrx_dle_control_has_hangup_marker,
)


def test_raw_dle_s_in_stream_is_control_per_v253():
    """Sans echappement DLE-DLE, 0x10 puis 's' est un code controle (pas du PCM)."""
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, 0x73, 0x80, 0x90])) is True


def test_pcm_without_dle_bytes_is_safe():
    scanner = _VrxHangupScanner()
    data = bytes(range(32, 200)) * 20
    assert scanner.feed(data) is False


def test_pcm_escaped_dle_is_ignored():
    """DLE-DLE dans le flux = octet PCM 0x10, pas un code controle."""
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, 0x10, 0x73])) is False


def test_real_dle_silence_marker_detected():
    """DLE + s (sans double DLE avant) = fin de session."""
    scanner = _VrxHangupScanner()
    assert scanner.feed(bytes([0x10, ord("s")])) is True


def test_no_carrier_text_detected():
    scanner = _VrxHangupScanner()
    assert scanner.feed(b"\r\nNO CARRIER\r\n") is True


def test_legacy_buffer_helper_still_works_on_control_tail():
    assert _vrx_dle_control_has_hangup_marker(bytes([0x10, ord("s")])) is True
    assert _vrx_buffer_has_hangup_marker(b"NO CARRIER") is True
