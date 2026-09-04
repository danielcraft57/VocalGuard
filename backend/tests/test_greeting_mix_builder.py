"""
Tests builder mix accueil (sans edge-tts reseau).
"""

from pathlib import Path

from pydub.generators import Sine

from backend.voice.greeting_mix_builder import GreetingMixParams, build_greeting_mix_from_tts_source
from backend.voice.modem_profile import USR_VOICE_PROFILE


def _write_tone_wav(path: Path, *, ms: int = 400, rate: int = 22050) -> None:
    """Petit ton mono pour tests mix."""
    tone = Sine(440).to_audio_segment(duration=ms).set_frame_rate(rate).set_channels(1)
    (tone - 12).export(str(path), format="wav")


def test_build_greeting_mix_jingle(tmp_path: Path):
    """Mix jingle + voix produit un WAV modem non vide."""
    tts = tmp_path / "tts.wav"
    intro = tmp_path / "intro.wav"
    out = tmp_path / "out.wav"
    _write_tone_wav(tts, ms=600)
    _write_tone_wav(intro, ms=800)

    params = GreetingMixParams(
        intro_mode="jingle",
        intro_variant="tesla",
        intro_sec=1.0,
        crossfade_ms=200,
        sample_rate=USR_VOICE_PROFILE.sample_rate,
        sample_width=USR_VOICE_PROFILE.sample_width,
        append_beep=False,
        output="modem",
    )
    result = build_greeting_mix_from_tts_source(
        tts,
        out,
        params=params,
        intro_path=intro,
    )
    assert result == out
    assert out.is_file()
    assert out.stat().st_size > 500


def test_build_greeting_mix_voice_listen(tmp_path: Path):
    """Mode voice exporte un apercu listen sans intro."""
    tts = tmp_path / "tts.wav"
    out = tmp_path / "listen.wav"
    _write_tone_wav(tts, ms=500)
    params = GreetingMixParams(
        intro_mode="none",
        sample_rate=USR_VOICE_PROFILE.sample_rate,
        sample_width=USR_VOICE_PROFILE.sample_width,
        append_beep=False,
        output="voice",
    )
    build_greeting_mix_from_tts_source(tts, out, params=params)
    assert out.is_file()
    assert out.stat().st_size > 200
