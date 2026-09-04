"""
Tests client HTTP node15 (mocks httpx).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.voice.node15_voice_client import Node15VoiceClient


@pytest.mark.asyncio
async def test_transcribe_sends_token_and_mode():
    """transcribe poste multipart + token."""
    client = Node15VoiceClient("http://node15.test:8100", token="secret", timeout_sec=5)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"text": "bonjour", "cues": [], "engine": "whisper"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("backend.voice.node15_voice_client.httpx.AsyncClient", return_value=mock_client):
        out = await client.transcribe(b"\x00\x01" * 100, mode="live")
    assert out["text"] == "bonjour"
    kwargs = mock_client.post.await_args.kwargs
    assert kwargs["headers"]["X-STT-Token"] == "secret"
    assert kwargs["params"]["mode"] == "live"


@pytest.mark.asyncio
async def test_intent_predict_parses_top():
    client = Node15VoiceClient("http://node15.test:8100")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "top_predictions": [{"tag": "prise_rdv", "score": 0.8}]
    }
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("backend.voice.node15_voice_client.httpx.AsyncClient", return_value=mock_client):
        preds = await client.intent_predict("rdv")
    assert preds[0]["tag"] == "prise_rdv"


@pytest.mark.asyncio
async def test_tts_returns_bytes():
    client = Node15VoiceClient("http://node15.test:8100")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"content-type": "audio/mpeg"}
    mock_resp.content = b"ID3fake"
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("backend.voice.node15_voice_client.httpx.AsyncClient", return_value=mock_client):
        data = await client.tts("bonjour")
    assert data.startswith(b"ID3")
