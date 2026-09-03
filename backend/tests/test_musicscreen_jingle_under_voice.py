"""Verifie que le jingle MusicScreen continue sous la voix."""

from backend.core.incoming_call_audio import resolve_intro_voice_bed_gain_db
from backend.core.incoming_call_types import IncomingCallAudioConfig
from backend.voice.audio_utils import (
    _crossfade_musicscreen_jingle_voice,
    combine_intro_voice_crossfade,
    load_audio_segment_modem,
    write_beep_wav_8k,
)


def test_resolve_intro_voice_bed_enabled_for_musicscreen():
    """Le reglage bed s'applique aux jingles MusicScreen (suite du jingle, pas bed synth)."""
    audio = IncomingCallAudioConfig(
        greeting_intro_mode="jingle",
        greeting_intro_variant="tesla",
        greeting_intro_voice_bed_db=-20.0,
    )
    assert resolve_intro_voice_bed_gain_db(audio, "tesla") == -20.0


def test_musicscreen_jingle_continues_under_voice(tmp_path):
    """Le mix avec variante tesla prolonge le jingle sous la voix."""
    from pydub import AudioSegment

    intro = tmp_path / "intro.wav"
    voice = tmp_path / "voice.wav"
    write_beep_wav_8k(intro, duration_ms=4000, freq_hz=440)
    write_beep_wav_8k(voice, duration_ms=2000, freq_hz=880)
    out = tmp_path / "mix.wav"

    intro_seg = load_audio_segment_modem(intro)
    voice_seg = load_audio_segment_modem(voice)
    mixed = _crossfade_musicscreen_jingle_voice(
        intro_seg,
        voice_seg,
        handoff_ms=1200,
        crossfade_ms=300,
        music_under_gain_db=-18.0,
    )
    voice_only = _crossfade_musicscreen_jingle_voice(
        intro_seg,
        voice_seg,
        handoff_ms=1200,
        crossfade_ms=300,
        music_under_gain_db=0.0,
    )
    assert mixed.dBFS != voice_only.dBFS

    combine_intro_voice_crossfade(
        intro,
        voice,
        out,
        crossfade_ms=300,
        intro_max_ms=1200,
        intro_variant="tesla",
        voice_bed_gain_db=-18.0,
    )
    assert out.is_file()
    result = AudioSegment.from_file(str(out))
    assert len(result) > 1500
