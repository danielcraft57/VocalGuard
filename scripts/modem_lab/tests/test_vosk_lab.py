"""Tests légers sur le catalogue Vosk lab (sans téléchargement)."""

from pathlib import Path

from labaudio.vosk_lab import FRENCH_MODELS, VoskLabProfile, default_cache_root, is_plausible_vosk_dir


def test_catalog_has_three_fr_models() -> None:
    assert "small-fr" in FRENCH_MODELS
    assert "fr-0.22" in FRENCH_MODELS
    assert "pguyot-small" in FRENCH_MODELS
    for slug, m in FRENCH_MODELS.items():
        assert m["url"].startswith("https://")
        assert m["dir_name"]


def test_is_plausible_empty_dir_false(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    assert not is_plausible_vosk_dir(d)


def test_profile_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "prof.json"
    pr = VoskLabProfile(model_slug="small-fr", model_path="/x/model", cache_root="/cache")
    from labaudio.vosk_lab import load_profile, save_profile

    save_profile(pr, p)
    loaded = load_profile(p)
    assert loaded.model_slug == "small-fr"
    assert loaded.model_path == "/x/model"


def test_default_cache_under_modem_lab() -> None:
    assert "vosk_models" in str(default_cache_root())
