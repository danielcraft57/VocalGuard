"""Tests ecoute directe jingle MusicScreen."""

from pathlib import Path

from backend.voice.musicscreen_jingles import musicscreen_jingle_path


def test_musicscreen_jingle_mp3_on_disk():
    """Le jingle tesla est disponible pour streaming API."""
    repo = Path(__file__).resolve().parents[2]
    path = musicscreen_jingle_path(repo, "tesla")
    assert path is not None
    assert path.suffix.lower() == ".mp3"
    assert path.stat().st_size > 1000
