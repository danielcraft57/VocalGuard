"""Tests accueils multi-audiences et chemins cache modem."""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.config import Config
from backend.core.greeting_audiences import (
    audience_from_profile,
    ensure_audience_slots,
    greeting_text_for_audience,
    normalize_audience,
    resolve_audio_for_audience,
)
from backend.core.incoming_call_types import IncomingCallAudioConfig, IncomingCallSettingsData
from backend.services.greeting_audio_service import (
    greeting_modem_active_meta_path,
    greeting_modem_active_wav_path,
)


def test_normalize_and_profile_mapping() -> None:
    assert normalize_audience("connu") == "known"
    assert normalize_audience(None) == "unknown"
    assert audience_from_profile("permitted") == "known"
    assert audience_from_profile("blocked") == "commercial"


def test_greeting_modem_paths_per_audience() -> None:
    cfg = SimpleNamespace(base_path=r"C:\fake\vocalguard")
    unknown = greeting_modem_active_wav_path(cfg)  # type: ignore[arg-type]
    commercial = greeting_modem_active_wav_path(cfg, "commercial")  # type: ignore[arg-type]
    known = greeting_modem_active_wav_path(cfg, "known")  # type: ignore[arg-type]
    assert unknown.name == "greeting_modem_active.wav"
    assert commercial.name == "greeting_modem_active_commercial.wav"
    assert known.name == "greeting_modem_active_known.wav"
    assert greeting_modem_active_meta_path(cfg, "commercial").name.endswith(  # type: ignore[arg-type]
        "greeting_modem_active_commercial.meta.json"
    )


def test_resolve_audio_for_audience_overrides_text() -> None:
    audio = IncomingCallAudioConfig(greeting_tts_text="Global")
    ensure_audience_slots(audio)
    audio.audiences["known"].greeting_tts_text = "Salut ami"
    settings = IncomingCallSettingsData(audio=audio)
    resolved = resolve_audio_for_audience(settings, "known")
    text = greeting_text_for_audience(Config(), resolved, "known")
    assert "Salut ami" in text


def test_prepare_audience_settings_importable() -> None:
    from backend.services.greeting_audio_service import _prepare_audience_settings

    assert callable(_prepare_audience_settings)
