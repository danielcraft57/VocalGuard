"""Tests CID / planning ligne / escape DLE (sans modem physique)."""

from __future__ import annotations

from datetime import datetime

from backend.core.incoming_line_schedule import apply_schedule_to_auto_answer, resolve_scheduled_line_mode
from backend.core.modem_handler import _escape_dle_pcm
from backend.core.phone_cid import classify_cid_outcome, is_masked_cid_token, normalize_cid_value


def test_normalize_cid_filters_masked_tokens() -> None:
    """O/P/PRIVATE ne doivent pas devenir un faux numero."""
    assert normalize_cid_value("0612345678") == "0612345678"
    assert normalize_cid_value("O") is None
    assert normalize_cid_value("P") is None
    assert normalize_cid_value("PRIVATE") is None
    assert normalize_cid_value('  "OUT_OF_AREA"  ') is None
    assert is_masked_cid_token("unavailable")


def test_classify_cid_outcome() -> None:
    assert classify_cid_outcome(caller_id="0612", source="ring") == "ok"
    assert classify_cid_outcome(caller_id=None, source="ring", timed_out=True) == "timeout"
    assert classify_cid_outcome(caller_id="0612", source="ata") == "ata"


def test_escape_dle_pcm_doubles_0x10() -> None:
    raw = bytes([0x00, 0x10, 0x20, 0x10])
    assert _escape_dle_pcm(raw) == bytes([0x00, 0x10, 0x10, 0x20, 0x10, 0x10])
    assert _escape_dle_pcm(b"\x01\x02") == b"\x01\x02"


def test_schedule_night_voicemail() -> None:
    schedule = {
        "enabled": True,
        "rules": [
            {"days": [0, 1, 2, 3, 4], "start": "22:00", "end": "07:00", "mode": "voicemail"},
        ],
    }
    # Mardi 23h -> voicemail
    night = datetime(2026, 8, 25, 23, 0)  # mardi
    assert resolve_scheduled_line_mode(schedule, now=night) == "voicemail"
    # Mardi 10h -> hors creneau
    day = datetime(2026, 8, 25, 10, 0)
    assert resolve_scheduled_line_mode(schedule, now=day) is None


class _Cfg:
    incoming_auto_answer = False
    incoming_line_schedule = {
        "enabled": True,
        "rules": [{"start": "00:00", "end": "23:59", "mode": "voicemail"}],
    }


def test_apply_schedule_overrides_switch() -> None:
    assert apply_schedule_to_auto_answer(_Cfg()) is True
