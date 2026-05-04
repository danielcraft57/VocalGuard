#!/usr/bin/env python3
"""Tests format SUB/WebVTT (sans modèle Vosk)."""

from pathlib import Path

import pytest

from labaudio.vosk_stt import (
    TimedUtterance,
    TimedWord,
    format_timestamp_sub,
    format_timestamp_vtt,
    offset_timed_utterances,
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


def test_offset_timed_utterances_zero_is_identity() -> None:
    uts = [TimedUtterance(0.5, 1.0, "x", (TimedWord(0.5, 0.8, "x"),))]
    assert offset_timed_utterances(uts, 0.0)[0].start_sec == 0.5


def test_offset_timed_utterances_shifts_utterance_and_words() -> None:
    uts = [TimedUtterance(0.0, 1.0, "allo", (TimedWord(0.0, 0.5, "allo"),))]
    out = offset_timed_utterances(uts, 4.52)
    assert out[0].start_sec == pytest.approx(4.52)
    assert out[0].end_sec == pytest.approx(5.52)
    assert out[0].words[0].start_sec == pytest.approx(4.52)


def test_write_subrip_collapses_internal_newlines(tmp_path: Path) -> None:
    """Le corps d’une entrée SRT reste une ligne logique (pas de retours parasites)."""
    utt = [TimedUtterance(start_sec=0.0, end_sec=1.0, text="ligne un\nligne deux", words=())]
    sub_p = tmp_path / "nl.srt"
    write_subrip(sub_p, utt)
    sub_txt = sub_p.read_text(encoding="utf-8")
    assert "ligne un ligne deux" in sub_txt
    assert "\nligne deux\n" not in sub_txt


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
