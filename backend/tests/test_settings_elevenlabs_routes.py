"""
Tests routes settings ElevenLabs (liste voix, apercu sans appel reseau reel).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.dependencies import get_config, reset_config_singleton
from backend.api.routes import settings as settings_routes
from backend.core.config import Config


@pytest.fixture()
def settings_client(isolated_work_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """App minimale avec router settings."""
    reset_config_singleton()
    cfg = Config()
    cfg.base_path = isolated_work_dir
    cfg.elevenlabs_api_key = None
    cfg.elevenlabs_voice_id = "JBFqnCBsd6RMkjVDRZzb"
    cfg.elevenlabs_model_id = "eleven_multilingual_v2"
    monkeypatch.chdir(isolated_work_dir)

    app = FastAPI()
    app.include_router(settings_routes.router, prefix="/api/v1")

    app.dependency_overrides[get_config] = lambda: cfg
    client = TestClient(app)
    yield client, cfg
    reset_config_singleton()


def test_get_elevenlabs_voices_without_key(settings_client) -> None:
    """GET voices : catalogue curate si pas de clef."""
    client, _cfg = settings_client
    r = client.get("/api/v1/settings/incoming-call/elevenlabs/voices")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["source"] == "none"
    assert len(body["voices"]) > 0


def test_post_elevenlabs_preview_requires_api_key(settings_client) -> None:
    """POST preview : 400 sans ELEVENLABS_API_KEY."""
    client, _cfg = settings_client
    r = client.post(
        "/api/v1/settings/incoming-call/elevenlabs/preview",
        json={"voice_id": "onwK4e9ZLuTAKqWW03F9", "text": "Test"},
    )
    assert r.status_code == 400
    assert "ELEVENLABS" in (r.json().get("detail") or "")


def test_post_elevenlabs_preview_returns_mpeg(settings_client) -> None:
    """POST preview : fichier audio si synthese mockee."""
    client, cfg = settings_client
    cfg.elevenlabs_api_key = "secret"

    def _fake_synth(**kwargs: object) -> Path:
        out = kwargs["out_path"]
        assert isinstance(out, Path)
        out.write_bytes(b"\xff\xfb" + b"\x00" * 300)
        return out

    with patch(
        "backend.api.routes.settings.synthesize_elevenlabs_mp3",
        side_effect=_fake_synth,
    ):
        r = client.post(
            "/api/v1/settings/incoming-call/elevenlabs/preview",
            json={"voice_id": "onwK4e9ZLuTAKqWW03F9", "text": "Apercu court"},
        )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/mpeg")
    assert len(r.content) > 200