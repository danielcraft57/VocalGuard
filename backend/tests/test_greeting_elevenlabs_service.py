"""
Tests accueil ElevenLabs : pas de node15 / Edge pour provider elevenlabs.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import Config
from backend.core.incoming_call_types import IncomingCallAudioConfig
from backend.services.greeting_audio_service import (
    _synthesize_voice_modem_wav,
    build_greeting_listen_preview,
)
from backend.voice.audio_utils import write_beep_wav_8k
from backend.voice.synthesis import VoiceSynthesis


@pytest.mark.asyncio
async def test_synthesize_voice_modem_wav_elevenlabs_path(
    isolated_work_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tts_provider=elevenlabs appelle synthesize_elevenlabs_mp3, pas synthesis.speak."""
    config = Config()
    config.base_path = isolated_work_dir
    config.elevenlabs_api_key = "test-key"

    calls: dict[str, int] = {"eleven": 0, "edge": 0}

    def _fake_eleven(**kwargs: object) -> Path:
        calls["eleven"] += 1
        out = kwargs["out_path"]
        assert isinstance(out, Path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-mp3")
        return out

    async def _fake_speak(self, *args: object, **kwargs: object) -> None:
        calls["edge"] += 1
        return None

    monkeypatch.setattr(
        "backend.voice.elevenlabs_client.synthesize_elevenlabs_mp3",
        _fake_eleven,
    )
    monkeypatch.setattr(VoiceSynthesis, "speak", _fake_speak)

    def _fake_modem(src: Path, out: Path, **kwargs: object) -> None:
        write_beep_wav_8k(out, duration_ms=120)

    monkeypatch.setattr(
        "backend.services.greeting_audio_service.tts_source_to_modem_wav",
        _fake_modem,
    )

    audio = IncomingCallAudioConfig(
        tts_provider="elevenlabs",
        elevenlabs_voice_id="voice-xyz",
    )
    synthesis = VoiceSynthesis(config)
    out = isolated_work_dir / "modem_voice.wav"
    result = await _synthesize_voice_modem_wav(
        config,
        synthesis,
        "Bonjour ElevenLabs",
        audience="unknown",
        audio=audio,
        out_path=out,
    )
    assert result == out
    assert out.is_file()
    assert calls["eleven"] == 1
    assert calls["edge"] == 0


@pytest.mark.asyncio
async def test_synthesize_voice_modem_wav_elevenlabs_requires_api_key(
    isolated_work_dir: Path,
) -> None:
    """Sans ELEVENLABS_API_KEY, erreur explicite."""
    config = Config()
    config.base_path = isolated_work_dir
    config.elevenlabs_api_key = None
    audio = IncomingCallAudioConfig(tts_provider="elevenlabs")
    synthesis = VoiceSynthesis(config)
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        await _synthesize_voice_modem_wav(
            config,
            synthesis,
            "Hi",
            audio=audio,
            out_path=isolated_work_dir / "v.wav",
        )


@pytest.mark.asyncio
async def test_build_preview_skips_remote_mix_for_elevenlabs(
    isolated_work_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_greeting_listen_preview ne doit pas appeler try_remote_greeting_mix si elevenlabs."""
    config = Config()
    config.base_path = isolated_work_dir
    config.elevenlabs_api_key = "k"

    remote = AsyncMock(return_value=isolated_work_dir / "remote.wav")

    def _fake_eleven(**kwargs: object) -> Path:
        p = kwargs["out_path"]
        assert isinstance(p, Path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"mp3")
        return p

    def _fake_modem(src: Path, out: Path, **kwargs: object) -> None:
        write_beep_wav_8k(out, duration_ms=80)

    def _fake_mix_sync(
        config: Config,
        settings: object,
        voice_wav: Path,
        *,
        out_modem: Path,
    ) -> None:
        write_beep_wav_8k(out_modem, duration_ms=200)

    async def _noop_init(self) -> None:
        self.initialized = True

    monkeypatch.setattr(
        "backend.services.greeting_audio_service.try_remote_greeting_mix",
        remote,
    )
    monkeypatch.setattr(
        "backend.voice.elevenlabs_client.synthesize_elevenlabs_mp3",
        _fake_eleven,
    )
    monkeypatch.setattr(
        "backend.services.greeting_audio_service.tts_source_to_modem_wav",
        _fake_modem,
    )
    monkeypatch.setattr(
        "backend.services.greeting_audio_service._build_modem_greeting_wav_sync",
        _fake_mix_sync,
    )
    monkeypatch.setattr(
        "backend.services.greeting_audio_service.export_listen_preview_wav",
        lambda src, dst, **kw: write_beep_wav_8k(dst, duration_ms=100),
    )
    monkeypatch.setattr(VoiceSynthesis, "initialize", _noop_init)

    override = {"tts_provider": "elevenlabs", "elevenlabs_voice_id": "v1"}
    path = await build_greeting_listen_preview(
        config,
        audio_override=override,
        preview_mode="full",
        audience="unknown",
    )
    assert path.is_file()
    remote.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_manager_regenerate_skips_remote_for_elevenlabs(
    isolated_work_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """regenerate_greeting_cache : provider elevenlabs -> pas de try_remote_greeting_mix."""
    from backend.core.call_manager import CallManager

    config = Config()
    config.base_path = isolated_work_dir
    config.elevenlabs_api_key = "k"
    ivr = isolated_work_dir / "ivr_wav"
    ivr.mkdir(parents=True, exist_ok=True)
    (isolated_work_dir / "data").mkdir(parents=True, exist_ok=True)

    db = MagicMock()
    cm = CallManager(config, db)
    cm._ensure_ivr_wav_dir = lambda: ivr  # type: ignore[method-assign]
    cm.reload_incoming_policy = lambda: None  # type: ignore[method-assign]
    cm._refresh_early_greeting_wav = lambda: None  # type: ignore[method-assign]
    cm._refresh_instant_ring_seize = lambda: None  # type: ignore[method-assign]
    cm._voicemail_goodbye_text = lambda: "Au revoir"  # type: ignore[method-assign]
    cm._ivr_cache = MagicMock()
    cm.modem = MagicMock(voice_profile=None)

    remote = AsyncMock()
    fake_wav = isolated_work_dir / "voice.wav"
    write_beep_wav_8k(fake_wav, duration_ms=100)

    async def _fake_synth(*args: object, **kwargs: object) -> Path:
        return fake_wav

    def _fake_build_sync(
        cfg: Config,
        settings: object,
        voice_wav: Path,
        *,
        out_modem: Path,
    ) -> None:
        write_beep_wav_8k(out_modem, duration_ms=300)

    monkeypatch.setattr(
        "backend.services.greeting_audio_service.try_remote_greeting_mix",
        remote,
    )
    monkeypatch.setattr(
        "backend.services.greeting_audio_service._synthesize_voice_modem_wav",
        _fake_synth,
    )
    monkeypatch.setattr(
        "backend.services.greeting_audio_service._build_modem_greeting_wav_sync",
        _fake_build_sync,
    )
    monkeypatch.setattr(
        "backend.voice.audio_utils.write_beep_wav_8k",
        write_beep_wav_8k,
    )

    override = {
        "tts_provider": "elevenlabs",
        "elevenlabs_voice_id": "v-prod",
        "greeting_tts_text": "Accueil test",
    }
    data = await cm.regenerate_greeting_cache(
        audience="unknown",
        audio_override=override,
    )
    remote.assert_not_awaited()
    assert data.get("track_wav")
    active = ivr / "greeting_modem_active.wav"
    assert active.is_file()