#!/usr/bin/env python3
"""
Applique la configuration accueil mode track (Whispering Iceland + Vivienne).

Usage (sur le Pi ou en local) :
  cd /opt/vocalguard
  source venv/bin/activate
  python scripts/apply_incoming_audio_track.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import Config
from backend.core.incoming_call_settings import (
    apply_incoming_call_settings,
    load_incoming_call_settings,
    save_incoming_call_settings,
)
from backend.core.incoming_line_mode import apply_incoming_line_mode
from backend.voice.voice_paths import WHISPERING_ICELAND_MP3


def main() -> int:
    """Persiste la config track + repondeur (bip + enregistrement)."""
    config = Config()
    config.base_path = ROOT
    settings = load_incoming_call_settings(config)

    settings.active_preset = "voicemail"
    preset = settings.presets.get("voicemail")
    if preset:
        preset.screened_actions = ["answer", "greeting", "record"]
        preset.blocked_actions = ["answer", "greeting", "hangup"]

    audio = settings.audio
    audio.greeting_source = "tts"
    audio.greeting_intro_mode = "track"
    audio.greeting_intro_wav_path = str(WHISPERING_ICELAND_MP3).replace("\\", "/")
    audio.greeting_intro_sec = 0.0
    audio.greeting_intro_crossfade_ms = 450
    audio.greeting_intro_voice_gain_db = 5.0
    audio.greeting_intro_track_duck_db = 0.0
    audio.greeting_intro_music_offset_sec = 0.0
    audio.edge_tts_voice = "fr-FR-VivienneMultilingualNeural"
    audio.edge_tts_pitch = "+7Hz"
    audio.edge_tts_rate = "+0%"
    audio.greeting_tts_text = (
        "Bonjour, Monsieur Daniel est absent. Merci de laisser un message apres le bip."
    )
    audio.record_beep = "wav"
    audio.record_beep_wav_path = "resources/voice/system/beep.wav"

    vm = settings.voicemail
    vm.require_dtmf = False
    vm.max_record_sec = 120
    vm.silence_end_sec = 4.0

    apply_incoming_call_settings(config, settings)
    apply_incoming_line_mode(config, "voicemail")
    save_incoming_call_settings(config, settings)

    music = ROOT / WHISPERING_ICELAND_MP3
    if not music.is_file():
        print(f"ATTENTION : piste absente ({music})", file=sys.stderr)
        return 2

    print("OK incoming_call_settings.yaml (mode track, Vivienne, bip + record)")
    print(f"  piste : {audio.greeting_intro_wav_path}")
    print(f"  solo  : {audio.greeting_intro_sec}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
