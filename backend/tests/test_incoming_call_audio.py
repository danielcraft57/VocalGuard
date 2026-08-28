"""Tests module incoming_call_audio."""

from pathlib import Path

from backend.core.config import Config
from backend.core.incoming_call_audio import (
    blocked_message_text,
    ensure_default_voice_assets,
    greeting_text,
    resolve_resource_path,
)
from backend.core.incoming_call_settings import load_incoming_call_settings


def test_greeting_text_override():
    config = Config()
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_tts_text = "Bonjour test"
    assert greeting_text(config, settings) == "Bonjour test"


def test_blocked_message_default():
    config = Config()
    settings = load_incoming_call_settings(config)
    assert "bloque" in blocked_message_text(settings).lower()


def test_ensure_voice_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = Config()
    config.base_path = tmp_path
    ensure_default_voice_assets(config)
    beep = tmp_path / "resources" / "voice" / "beep.wav"
    assert beep.is_file()
    assert resolve_resource_path(config, "resources/voice/beep.wav") == beep.resolve()
