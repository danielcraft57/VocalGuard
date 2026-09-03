"""Tests apercu intro brute (sans pipeline modem)."""

from pathlib import Path

from backend.core.config import Config
from backend.core.incoming_call_settings import load_incoming_call_settings
from backend.services.greeting_audio_service import _build_intro_listen_preview_sync
from backend.voice.audio_utils import export_raw_listen_preview, listen_preview_response_meta


def test_export_raw_listen_preview_copies_mp3(tmp_path):
    """Un MP3 est copie tel quel pour l'ecoute navigateur."""
    repo = Path(__file__).resolve().parents[2]
    src = repo / "resources" / "voice" / "jingles" / "Tesla-Jingle.mp3"
    if not src.is_file():
        return
    out = export_raw_listen_preview(src, tmp_path / "preview")
    assert out.suffix == ".mp3"
    assert out.is_file()
    assert out.stat().st_size == src.stat().st_size


def test_listen_preview_response_meta_mp3():
    """Le type MIME MP3 est expose pour le navigateur."""
    media_type, filename = listen_preview_response_meta(Path("x.mp3"))
    assert media_type == "audio/mpeg"
    assert filename.endswith(".mp3")


def test_build_intro_listen_preview_raw_jingle():
    """L'apercu intro renvoie le MP3 MusicScreen sans conversion modem."""
    repo = Path(__file__).resolve().parents[2]
    src = repo / "resources" / "voice" / "jingles" / "Tesla-Jingle.mp3"
    if not src.is_file():
        return
    config = Config()
    config.base_path = repo
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_intro_mode = "jingle"
    settings.audio.greeting_intro_variant = "tesla"
    out = _build_intro_listen_preview_sync(config, settings, out_base=repo / "data" / "audio_previews" / "_test_intro")
    assert out.suffix == ".mp3"
    assert out.stat().st_size == src.stat().st_size
