"""Tests catalogue prereglages audio."""

from backend.voice.audio_presets import (
    get_audio_preset,
    list_audio_presets,
)


def test_list_audio_presets_has_three_categories():
    """Le catalogue expose voix, intro et outro."""
    catalog = list_audio_presets()
    assert set(catalog.keys()) == {"voice", "intro", "outro"}
    assert len(catalog["voice"]) >= 5
    assert len(catalog["intro"]) >= 5
    assert len(catalog["outro"]) >= 4


def test_voice_preset_contains_tts_fields():
    """Un preset voix fournit voix, debit, hauteur et gain."""
    preset = get_audio_preset("voice", "denise_modem")
    assert preset is not None
    values = preset["values"]
    assert values["edge_tts_voice"] == "fr-FR-DeniseNeural"
    assert "edge_tts_rate" in values
    assert "tts_voice_gain_db" in values
    assert values.get("greeting_tts_text")


def test_intro_preset_jingle_variant():
    """Un preset intro jingle reference une variante MusicScreen."""
    preset = get_audio_preset("intro", "tesla_court")
    assert preset is not None
    values = preset["values"]
    assert values["greeting_intro_mode"] == "jingle"
    assert values["greeting_intro_variant"] == "tesla"


def test_outro_preset_beep_modes():
    """Les presets outro couvrent wav, dtmf et none."""
    modes = set()
    for row in list_audio_presets()["outro"]:
        modes.add(row["values"].get("record_beep"))
    assert {"wav", "dtmf", "none"}.issubset(modes)
