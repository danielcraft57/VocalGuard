"""Tests légers sur le catalogue Vosk lab (sans téléchargement)."""

import shutil
import sys
from pathlib import Path

import pytest

LAB_DIR = Path(__file__).resolve().parents[1]
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

from labaudio.vosk_lab import FRENCH_MODELS, VoskLabProfile, default_cache_root, is_plausible_vosk_dir


def test_catalog_has_three_fr_models() -> None:
    assert "small-fr" in FRENCH_MODELS
    assert "fr-0.22" in FRENCH_MODELS
    assert "pguyot-small" in FRENCH_MODELS
    for slug, m in FRENCH_MODELS.items():
        assert m["url"].startswith("https://")
        assert m["dir_name"]


def test_is_plausible_empty_dir_false() -> None:
    d = LAB_DIR / "generated" / "_pytest_vosk_empty"
    d.mkdir(parents=True, exist_ok=True)
    try:
        assert not is_plausible_vosk_dir(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_profile_roundtrip() -> None:
    d = LAB_DIR / "generated" / "_pytest_vosk_prof"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "prof.json"
    pr = VoskLabProfile(model_slug="small-fr", model_path="/x/model", cache_root="/cache")
    from labaudio.vosk_lab import load_profile, save_profile

    try:
        save_profile(pr, p)
        loaded = load_profile(p)
        assert loaded.model_slug == "small-fr"
        assert loaded.model_path == "/x/model"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_is_plausible_skips_permission_error_on_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si ``am/final.mdl`` est illisible (Windows), les autres marqueurs comptent encore."""
    d = LAB_DIR / "generated" / "_pytest_vosk_perm"
    d.mkdir(parents=True, exist_ok=True)
    orig_is_file = Path.is_file
    try:
        (d / "am").mkdir(exist_ok=True)
        (d / "am" / "final.mdl").write_bytes(b"x")
        (d / "model.conf").write_text("x", encoding="utf-8")

        def _is_file(self: Path) -> bool:
            if self.name == "final.mdl" and self.parent.name == "am":
                raise PermissionError("simulé")
            return orig_is_file(self)

        monkeypatch.setattr(Path, "is_file", _is_file)
        assert is_plausible_vosk_dir(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_default_cache_under_modem_lab() -> None:
    assert "vosk_models" in str(default_cache_root())
