"""Tests resolution chemins messages vocaux."""

from __future__ import annotations

from pathlib import Path

from backend.api.routes.voicemails import _resolve_voicemail_audio
from backend.core.config import Config


def test_resolve_voicemail_audio_relative(tmp_path_factory) -> None:
    """Le chemin messages/vm_*.wav est resolu sous base_path."""
    root = Path.cwd() / ".pytest_vg_tmp"
    root.mkdir(exist_ok=True)
    base = root / "vm_paths"
    if base.exists():
        for p in base.rglob("*"):
            if p.is_file():
                p.unlink()
    base.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.base_path = base
    messages = base / "messages"
    messages.mkdir(exist_ok=True)
    wav = messages / "vm_1_test.wav"
    wav.write_bytes(b"RIFF")
    found = _resolve_voicemail_audio(cfg, "messages/vm_1_test.wav")
    assert found is not None
    assert found == wav.resolve()


def test_resolve_voicemail_audio_rejects_traversal() -> None:
    """Refuse les chemins avec .."""
    root = Path.cwd() / ".pytest_vg_tmp" / "vm_paths2"
    root.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.base_path = root
    assert _resolve_voicemail_audio(cfg, "messages/../secrets.txt") is None
