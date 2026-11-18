"""
Tests client ElevenLabs (catalogue, resolution clef, synthese sans reseau).
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import Config
from backend.voice.elevenlabs_client import (
    curated_elevenlabs_voices,
    fetch_elevenlabs_voices_from_api,
    list_elevenlabs_voices,
    resolve_elevenlabs_api_key,
    resolve_elevenlabs_default_voice_id,
    resolve_elevenlabs_model_id,
    synthesize_elevenlabs_mp3,
)


def test_curated_voices_non_empty_and_fr_first() -> None:
    """Le catalogue offline contient des voix et peut prioriser le FR."""
    rows = curated_elevenlabs_voices(fr_first=True)
    assert len(rows) >= 10
    ids = {r["voice_id"] for r in rows}
    assert "onwK4e9ZLuTAKqWW03F9" in ids
    fr_flags = [r["recommended_fr"] for r in rows[:5]]
    assert any(fr_flags)


def test_resolve_elevenlabs_from_config_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clef, modele et voice id depuis Config ou variables d'env."""
    cfg = Config()
    cfg.elevenlabs_api_key = " cfg-key "
    cfg.elevenlabs_model_id = " eleven_flash_v2_5 "
    cfg.elevenlabs_voice_id = " custom-voice "
    assert resolve_elevenlabs_api_key(cfg) == "cfg-key"
    assert resolve_elevenlabs_model_id(cfg) == "eleven_flash_v2_5"
    assert resolve_elevenlabs_default_voice_id(cfg) == "custom-voice"

    cfg_env = Config()
    cfg_env.elevenlabs_api_key = None
    cfg_env.elevenlabs_voice_id = None
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-key")
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    assert resolve_elevenlabs_api_key(cfg_env) == "env-key"
    assert resolve_elevenlabs_default_voice_id(cfg_env) == "JBFqnCBsd6RMkjVDRZzb"


def test_list_elevenlabs_voices_without_api_key() -> None:
    """Sans clef : catalogue curate + warning UI."""
    cfg = Config()
    cfg.elevenlabs_api_key = None
    payload = list_elevenlabs_voices(cfg)
    assert payload["configured"] is False
    assert payload["source"] == "none"
    assert payload["voices"]
    assert "ELEVENLABS_API_KEY" in (payload.get("warning") or "")


def test_list_elevenlabs_voices_api_fallback_to_curated() -> None:
    """Avec clef mais sans voices_read : repli catalogue."""
    cfg = Config()
    cfg.elevenlabs_api_key = "secret"
    with patch(
        "backend.voice.elevenlabs_client.fetch_elevenlabs_voices_from_api",
        return_value=None,
    ):
        payload = list_elevenlabs_voices(cfg)
    assert payload["configured"] is True
    assert payload["source"] == "curated"
    assert payload["voices"]
    assert "voices_read" in (payload.get("warning") or "")


def test_fetch_elevenlabs_voices_http_error_returns_none() -> None:
    """HTTP 403 sur /v1/voices -> None (pas d'exception)."""
    import urllib.error

    err = urllib.error.HTTPError(
        url="https://api.elevenlabs.io/v1/voices",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=BytesIO(b'{"detail":"missing"}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        assert fetch_elevenlabs_voices_from_api("k") is None


def test_fetch_elevenlabs_voices_parses_api_payload() -> None:
    """Parse minimal de la liste API."""
    body = json.dumps(
        {
            "voices": [
                {
                    "voice_id": "abc123",
                    "name": "Test",
                    "labels": {"language": "French", "gender": "female"},
                }
            ]
        }
    ).encode("utf-8")

    class _Resp:
        def read(self) -> bytes:
            return body

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Resp()):
        rows = fetch_elevenlabs_voices_from_api("k")
    assert rows is not None
    assert rows[0]["voice_id"] == "abc123"
    assert rows[0]["source"] == "api"
    assert rows[0]["recommended_fr"] is True


def test_synthesize_elevenlabs_mp3_rejects_empty_text() -> None:
    """Texte vide interdit."""
    with pytest.raises(RuntimeError, match="vide"):
        synthesize_elevenlabs_mp3(
            api_key="k",
            text="   ",
            voice_id="v",
            out_path=Path("x.mp3"),
        )


def test_synthesize_elevenlabs_mp3_writes_audio(isolated_work_dir: Path) -> None:
    """Appel HTTP mocke : ecrit le MP3 sur disque."""
    fake_audio = b"\xff\xfb" + b"\x00" * 400

    class _Resp:
        def read(self) -> bytes:
            return fake_audio

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    out = isolated_work_dir / "el.mp3"
    with patch("urllib.request.urlopen", return_value=_Resp()):
        path = synthesize_elevenlabs_mp3(
            api_key="k",
            text="Bonjour test",
            voice_id="voice-x",
            model_id="eleven_multilingual_v2",
            out_path=out,
        )
    assert path == out
    assert out.read_bytes() == fake_audio


def test_synthesize_elevenlabs_truncates_long_text(isolated_work_dir: Path) -> None:
    """Garde-fou quota : texte tronque avant envoi API."""
    captured: dict[str, object] = {}

    class _Resp:
        def read(self) -> bytes:
            return b"\xff\xfb" + b"\x01" * 300

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _urlopen(req: object, timeout: int = 0) -> _Resp:
        captured["data"] = getattr(req, "data", None)
        return _Resp()

    out = isolated_work_dir / "long.mp3"
    long_text = "x" * 600
    with patch("urllib.request.urlopen", side_effect=_urlopen):
        synthesize_elevenlabs_mp3(
            api_key="k",
            text=long_text,
            voice_id="v",
            out_path=out,
        )
    body = json.loads(captured["data"])  # type: ignore[arg-type]
    assert len(body["text"]) <= 501