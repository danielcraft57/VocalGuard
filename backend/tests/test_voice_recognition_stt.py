"""Tests STT local vs distant (RAM prod)."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.core.config import Config
from backend.voice.recognition import VoiceRecognition


@pytest.mark.asyncio
async def test_initialize_skip_local_when_stt_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avec STT_SERVICE_URL, Vosk/Whisper ne sont pas charges."""
    monkeypatch.setenv("STT_SERVICE_URL", "http://node15.lan:8100")
    monkeypatch.delenv("VG_STT_LOCAL", raising=False)
    cfg = Config()
    cfg.stt_service_url = "http://node15.lan:8100"
    rec = VoiceRecognition(cfg)

    with patch(
        "backend.voice.stt_remote.check_stt_service_health",
        new_callable=AsyncMock,
        return_value=True,
    ):
        with patch.object(rec, "_init_vosk", new_callable=AsyncMock) as vosk_mock:
            with patch.object(rec, "_init_whisper", new_callable=AsyncMock) as wh_mock:
                await rec.initialize()

    vosk_mock.assert_not_called()
    wh_mock.assert_not_called()
    assert rec.vosk_model is None
    assert rec.whisper_model is None
    assert rec.is_available()


@pytest.mark.asyncio
async def test_initialize_loads_vosk_without_stt_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans STT distant, le moteur local reste utilisable."""
    monkeypatch.delenv("STT_SERVICE_URL", raising=False)
    monkeypatch.delenv("VG_STT_LOCAL", raising=False)
    cfg = Config()
    cfg.stt_service_url = None
    cfg.voice_recognition_engine = "vosk"
    rec = VoiceRecognition(cfg)

    with patch.object(rec, "_init_vosk", new_callable=AsyncMock, return_value=True) as vosk_mock:
        await rec.initialize()

    vosk_mock.assert_called_once()
