"""Tests moteur sons Prospector (sans lecture audio)."""

from __future__ import annotations

from desktop.prospector.sounds import ProspectorSounds


def test_volume_percent_clamp(monkeypatch) -> None:
    """Le volume est borne entre 0 et 100 %."""
    monkeypatch.setattr(ProspectorSounds, "_load_prefs", lambda self: None)
    monkeypatch.setattr(ProspectorSounds, "_save_prefs", lambda self: None)
    sounds = ProspectorSounds()
    sounds.set_volume_percent(150)
    assert sounds.volume_percent == 100
    sounds.set_muted(True)
    assert sounds.volume == 0.0
    sounds.set_muted(False)
    sounds.set_volume_percent(10)
    assert sounds.volume_percent == 10
