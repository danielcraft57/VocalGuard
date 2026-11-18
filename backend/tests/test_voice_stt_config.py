"""Config STT node15 : URL et token lus depuis .env (prod LAN)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from backend.core.config import Config


def test_stt_url_and_token_loaded_from_env(isolated_work_dir: Path) -> None:
    """STT_SERVICE_URL + STT_INTERNAL_TOKEN pour joindre node15."""
    env_file = isolated_work_dir / ".env"
    env_file.write_text(
        "STT_SERVICE_URL=http://node15.lan:8100\n"
        "STT_INTERNAL_TOKEN=shared-secret\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("STT_SERVICE_URL", None)
        os.environ.pop("STT_INTERNAL_TOKEN", None)
        cfg = Config(base_path=isolated_work_dir)
    assert cfg.stt_service_url == "http://node15.lan:8100"
    assert cfg.stt_internal_token == "shared-secret"


def test_tts_url_optional_separate_from_stt(isolated_work_dir: Path) -> None:
    """TTS_SERVICE_URL optionnel (conversation) : distinct de STT."""
    env_file = isolated_work_dir / ".env"
    env_file.write_text(
        "STT_SERVICE_URL=http://node15.lan:8100\n"
        "TTS_SERVICE_URL=http://node15.lan:8100\n",
        encoding="utf-8",
    )
    cfg = Config(base_path=isolated_work_dir)
    assert cfg.stt_service_url == "http://node15.lan:8100"
    assert cfg.tts_service_url == "http://node15.lan:8100"