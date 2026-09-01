"""Tests module incoming_call_audio."""

from pathlib import Path

from backend.core.config import Config
from backend.core.incoming_call_audio import (
    blocked_message_text,
    ensure_default_voice_assets,
    greeting_intro_path,
    greeting_text,
    resolve_resource_path,
)
from backend.core.incoming_call_settings import load_incoming_call_settings
from backend.voice.audio_utils import write_beep_wav_8k, write_greeting_jingle_wav_8k


def test_greeting_text_override():
    config = Config()
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_tts_text = "Bonjour test"
    assert greeting_text(config, settings) == "Bonjour test"


def test_blocked_message_default():
    config = Config()
    settings = load_incoming_call_settings(config)
    assert "bloque" in blocked_message_text(settings).lower()


def test_ensure_voice_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = Config()
    config.base_path = tmp_path
    ensure_default_voice_assets(config)
    beep = tmp_path / "resources" / "voice" / "system" / "beep.wav"
    assert beep.is_file()
    intro = tmp_path / "resources" / "voice" / "intros" / "default.wav"
    assert intro.is_file()
    assert resolve_resource_path(config, "resources/voice/system/beep.wav") == beep.resolve()


def test_greeting_intro_wav_default(tmp_path):
    """Intro WAV pop integree (mode wav par defaut)."""
    config = Config()
    config.base_path = tmp_path
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_intro_mode = "wav"
    # Copie un mini WAV modem
    src = tmp_path / "resources" / "voice" / "intros" / "default.wav"
    src.parent.mkdir(parents=True, exist_ok=True)
    write_greeting_jingle_wav_8k(src, duration_ms=1500)
    path = greeting_intro_path(config, settings.audio)
    assert path is not None
    assert path.is_file()


def test_combine_modem_wav_files(tmp_path):
    """Concat intro + message en un seul WAV modem."""
    from backend.voice.audio_utils import combine_modem_wav_files

    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    write_greeting_jingle_wav_8k(a, duration_ms=800)
    write_beep_wav_8k(b, duration_ms=400)
    out = tmp_path / "combined.wav"
    combine_modem_wav_files([a, b], out, gap_ms=200, max_first_ms=600)
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_greeting_intro_jingle(tmp_path):
    config = Config()
    config.base_path = tmp_path
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_intro_mode = "jingle"
    settings.audio.greeting_intro_variant = "sting_marimba"
    path = greeting_intro_path(config, settings.audio)
    assert path is not None
    assert path.is_file()
    assert path.stat().st_size > 1000


def test_combine_intro_voice_with_music_bed(tmp_path):
    """Fond musical leger sous la voix apres le fondu."""
    from backend.voice.audio_utils import combine_intro_voice_crossfade, write_greeting_intro_wav

    intro = tmp_path / "intro.wav"
    voice = tmp_path / "voice.wav"
    write_greeting_intro_wav(intro, variant="sting_marimba", duration_ms=2000)
    write_beep_wav_8k(voice, duration_ms=1200)
    out = tmp_path / "combined.wav"
    combine_intro_voice_crossfade(
        intro,
        voice,
        out,
        crossfade_ms=280,
        intro_max_ms=1500,
        intro_variant="sting_marimba",
        voice_bed_gain_db=-17.0,
        voice_mix_gain_db=5.0,
        voice_bed_variant="bed_marimba_warm",
    )
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_combine_music_track_voice_overlay(tmp_path):
    """Musique solo puis voix par-dessus (mode track)."""
    from backend.voice.audio_utils import combine_music_track_voice_overlay, write_greeting_jingle_wav_8k

    music = tmp_path / "music.wav"
    voice = tmp_path / "voice.wav"
    write_greeting_jingle_wav_8k(music, duration_ms=6000)
    write_beep_wav_8k(voice, duration_ms=1400)
    out = tmp_path / "track_mix.wav"
    combine_music_track_voice_overlay(
        music,
        voice,
        out,
        music_solo_ms=2500,
        voice_fade_ms=280,
        voice_mix_gain_db=4.0,
    )
    assert out.is_file()
    assert out.stat().st_size > 1000


def test_greeting_intro_track_path(tmp_path):
    """Mode track resout le chemin musical configure."""
    config = Config()
    config.base_path = tmp_path
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_intro_mode = "track"
    src = tmp_path / "resources" / "voice" / "music" / "test_track.wav"
    src.parent.mkdir(parents=True, exist_ok=True)
    write_greeting_jingle_wav_8k(src, duration_ms=2000)
    settings.audio.greeting_intro_wav_path = "resources/voice/music/test_track.wav"
    path = greeting_intro_path(config, settings.audio)
    assert path is not None
    assert path.is_file()


def test_normalize_pcm_u8_buffer_boosts_quiet_signal():
    """Les WAV u8 trop faibles sont re-gaines avant VTX."""
    from backend.voice.audio_utils import normalize_pcm_u8_buffer

    quiet = bytes([128, 129, 127, 130, 126] * 40)
    boosted = normalize_pcm_u8_buffer(quiet)
    quiet_peak = max(abs(b - 128) for b in quiet)
    boosted_peak = max(abs(b - 128) for b in boosted)
    assert boosted_peak > quiet_peak


def test_greeting_default_has_pauses():
    config = Config()
    settings = load_incoming_call_settings(config)
    settings.audio.greeting_tts_text = None
    config.voicemail_greeting = ""
    text = greeting_text(config, settings)
    assert "break time" in text


def test_write_telecom_intro(tmp_path):
    from backend.voice.audio_utils import write_telecom_voicemail_intro_wav

    for variant in ("sfr_a", "sfr_b", "sfr_c"):
        out = tmp_path / f"intro_{variant}.wav"
        write_telecom_voicemail_intro_wav(out, variant=variant, duration_ms=3000)
        assert out.is_file()
        assert out.stat().st_size > 500


def test_write_greeting_jingle(tmp_path):
    out = tmp_path / "jingle.wav"
    write_greeting_jingle_wav_8k(out, duration_ms=2000)
    assert out.is_file()
    assert out.stat().st_size > 500
