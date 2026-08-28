"""Tests extraction DTMF entrant (modem_handler)."""

from backend.core.modem_handler import extract_incoming_dtmf_digit


def test_extract_dtmf_isolated_digit():
    assert extract_incoming_dtmf_digit("1") == "1"
    assert extract_incoming_dtmf_digit(" # ") == "#"
    assert extract_incoming_dtmf_digit("*") == "*"


def test_extract_dtmf_urc():
    assert extract_incoming_dtmf_digit("DTMF: 5") == "5"
    assert extract_incoming_dtmf_digit("+VTD=2") == "2"


def test_extract_dtmf_ignores_at_responses():
    assert extract_incoming_dtmf_digit("OK") is None
    assert extract_incoming_dtmf_digit("CONNECT") is None
    assert extract_incoming_dtmf_digit("") is None
