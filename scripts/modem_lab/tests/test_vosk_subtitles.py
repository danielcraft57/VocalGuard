#!/usr/bin/env python3
"""Tests format SUB/WebVTT (sans modèle Vosk)."""

from pathlib import Path

import pytest

from labaudio.vosk_stt import (
    TimedUtterance,
    TimedWord,
    format_timestamp_sub,
    format_timestamp_vtt,
    write_subrip,
    write_webvtt,
)


@pytest.mark.parametrize(
    "sec,expected_sub",
    [
        (0.0, "00:00:00,000"),
        (1.234, "00:00:01,234"),
        (61.99, "00:01:01,990"),
    ],
)
def test_format_timestamp_sub(sec: float, expected_sub: str) -> None:
    assert format_timestamp_sub(sec) == expected_sub


def test_format_timestamp_vtt_comma_vs_dot() -> None:
    assert "." in format_timestamp_vtt(1.5)
    assert "," not in format_timestamp_vtt(1.5)


def test_write_sub_and_vtt_roundtrip(tmp_path: Path) -> None:
    utt = [
        TimedUtterance(
            start_sec=0.0,
            end_sec=1.0,
            text="Bonjour test",
            words=(TimedWord(0.0, 0.5, "bonjour"),),
        )
    ]
    sub_p = tmp_path / "t.srt"
    vtt_p = tmp_path / "t.vtt"
    write_subrip(sub_p, utt)
    write_webvtt(vtt_p, utt)
    sub_txt = sub_p.read_text(encoding="utf-8")
    assert "Bonjour test" in sub_txt
    assert "-->" in sub_txt
    vtt_txt = vtt_p.read_text(encoding="utf-8")
    assert vtt_txt.startswith("WEBVTT")
    assert "Bonjour test" in vtt_txt


def test_substitute_placeholders_in_intent_pack() -> None:
    from labaudio.intent_wav_pack import substitute_intent_placeholders

    s = substitute_intent_placeholders(
        "Je suis {{agent_name}} chez {{company_name}}.",
        {"agent_name": "Lee", "company_name": "Acme"},
    )
    assert s == "Je suis Lee chez Acme."
