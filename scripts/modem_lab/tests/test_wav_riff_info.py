"""Métadonnées RIFF LIST/INFO sur WAV (Explorateur Windows)."""

from __future__ import annotations

import sys
import wave
from pathlib import Path

_MODEM_LAB = Path(__file__).resolve().parents[1]
_ROOT = _MODEM_LAB.parent.parent
_SCRIPTS = _ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_MODEM_LAB))

from audio_utils import apply_wav_riff_info_tags  # noqa: E402


def _minimal_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(b"\x80" * 32)


def test_apply_wav_riff_info_tags_inserts_list_inam(tmp_path: Path) -> None:
    w = tmp_path / "x.wav"
    _minimal_wav(w)
    apply_wav_riff_info_tags(
        w,
        title="Titre démo",
        subtitle="Sous titre",
        artist="fr-FR-DeniseNeural",
        album="mon_pack",
        year="2026",
        track_number="01",
        genre="Prospection",
        media_origin="VocalGuard modem_lab",
        copyright_text="DanielCraft",
        parental_control="yes",
        parental_control_reason="langage",
        comment="intents: flow",
        software="VocalGuard test",
    )
    blob = w.read_bytes()
    assert blob[:4] == b"RIFF"
    assert blob[8:12] == b"WAVE"
    assert b"LIST" in blob
    assert b"INFO" in blob
    assert b"INAM" in blob
    assert "Titre démo".encode("cp1252") in blob
    assert b"IART" in blob
    assert b"IPRD" in blob
    assert b"ISBJ" in blob
    assert b"ICRD" in blob
    assert b"ITRK" in blob
    assert b"IGNR" in blob
    assert b"ISRC" in blob
    assert b"ICOP" in blob
    assert b"IKEY" in blob
    assert b"ICMT" in blob
    assert b"ISFT" in blob
    # lecture PCM toujours possible
    with wave.open(str(w), "rb") as wf:
        assert wf.getnframes() == 32


def test_apply_wav_riff_info_tags_idempotent_second_call(tmp_path: Path) -> None:
    w = tmp_path / "y.wav"
    _minimal_wav(w)
    apply_wav_riff_info_tags(w, title="A", artist="B", album="C")
    apply_wav_riff_info_tags(w, title="A2", artist="B2", album="C2")
    blob = w.read_bytes()
    assert blob.count(b"LIST") == 1
    assert b"INAM" in blob
    assert "A2".encode("utf-8") in blob
