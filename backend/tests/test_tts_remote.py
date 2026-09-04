"""
Tests resolution URL TTS et synthese distante.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.voice.synthesis import VoiceSynthesis
from backend.voice.tts_url import resolve_tts_service_url, resolve_tts_token


def test_resolve_tts_url_prefers_tts_service_url():
    """TTS_SERVICE_URL prioritaire sur STT_SERVICE_URL."""
    config = MagicMock()
    config.tts_service_url = "http://node15.lan:8100/"
    config.stt_service_url = "http://other.lan:8100"
    assert resolve_tts_service_url(config) == "http://node15.lan:8100"


def test_resolve_tts_url_falls_back_to_stt():
    """Sans TTS_SERVICE_URL, repli sur STT_SERVICE_URL."""
    config = MagicMock()
    config.tts_service_url = None
    config.stt_service_url = "http://node15.lan:8100"
    assert resolve_tts_service_url(config) == "http://node15.lan:8100"


def test_resolve_tts_url_none_when_empty():
    """Aucune URL distante si les deux sont vides."""
    config = MagicMock()
    config.tts_service_url = ""
    config.stt_service_url = None
    assert resolve_tts_service_url(config) is None


def test_resolve_tts_token():
    """Token STT reutilise pour le TTS distant."""
    config = MagicMock()
    config.stt_internal_token = " secret "
    assert resolve_tts_token(config) == "secret"


@pytest.mark.asyncio
async def test_speak_uses_remote_tts(tmp_path: Path):
    """speak() appelle node15 si TTS_SERVICE_URL est defini."""
    config = MagicMock()
    config.base_path = tmp_path
    config.voice_synthesis_engine = "edgetts"
    config.voice_language = "fr"
    config.edge_tts_voice = "fr-FR-DeniseNeural"
    config.edge_tts_rate = "-4%"
    config.edge_tts_pitch = "+3Hz"
    config.tts_service_url = "http://node15.test:8100"
    config.stt_service_url = None
    config.stt_internal_token = "tok"

    synthesis = VoiceSynthesis(config)
    out = tmp_path / "out.mp3"

    mock_client = MagicMock()
    mock_client.tts = AsyncMock(return_value=b"fake-mp3")

    with patch(
        "backend.voice.node15_voice_client.Node15VoiceClient",
        return_value=mock_client,
    ) as client_cls:
        result = await synthesis.speak("Bonjour", save_to_file=out, rate="-4%", pitch="+3Hz")

    assert result == out
    assert out.read_bytes() == b"fake-mp3"
    client_cls.assert_called_once()
    mock_client.tts.assert_awaited_once()
    call_kwargs = mock_client.tts.await_args
    assert call_kwargs.kwargs["voice"] == "fr-FR-DeniseNeural"
    assert call_kwargs.kwargs["rate"] == "-4%"
    assert call_kwargs.kwargs["pitch"] == "+3Hz"


@pytest.mark.asyncio
async def test_speak_falls_back_local_when_remote_fails(tmp_path: Path):
    """Si node15 KO, repli sur edge-tts local."""
    config = MagicMock()
    config.base_path = tmp_path
    config.voice_synthesis_engine = "edgetts"
    config.voice_language = "fr"
    config.edge_tts_voice = "fr-FR-DeniseNeural"
    config.edge_tts_rate = "+0%"
    config.edge_tts_pitch = "+0Hz"
    config.tts_service_url = "http://node15.test:8100"
    config.stt_service_url = None
    config.stt_internal_token = None

    synthesis = VoiceSynthesis(config)
    local_out = tmp_path / "local.mp3"

    with patch(
        "backend.voice.node15_voice_client.Node15VoiceClient",
        side_effect=RuntimeError("down"),
    ):
        with patch.object(
            synthesis,
            "_speak_edgetts",
            new=AsyncMock(return_value=local_out),
        ) as local_speak:
            result = await synthesis.speak("Test fallback")

    assert result == local_out
    local_speak.assert_awaited_once()


@pytest.mark.asyncio
async def test_greeting_mix_client_posts_multipart(tmp_path: Path):
    """Client greeting_mix envoie form + fichiers."""
    from backend.voice.node15_voice_client import Node15VoiceClient

    intro = tmp_path / "intro.wav"
    intro.write_bytes(b"RIFF....")
    client = Node15VoiceClient("http://node15.test:8100")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = b"RIFF-mixed"

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_cm.post = AsyncMock(return_value=mock_response)

    with patch("backend.voice.node15_voice_client.httpx.AsyncClient", return_value=mock_cm):
        data = await client.greeting_mix(
            "Bonjour",
            intro_mode="jingle",
            intro_path=intro,
            output="modem",
        )

    assert data == b"RIFF-mixed"
    mock_cm.post.assert_awaited_once()
    call_kwargs = mock_cm.post.await_args.kwargs
    assert call_kwargs["data"]["text"] == "Bonjour"
    assert call_kwargs["data"]["intro_mode"] == "jingle"
    assert call_kwargs["files"] is not None
