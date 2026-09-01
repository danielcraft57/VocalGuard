#!/usr/bin/env python3
"""
Regenere la voix TTS + le mix track d'accueil (Whispering Iceland + Vivienne).

Usage sur le Pi :
  cd /opt/vocalguard
  source venv/bin/activate
  python scripts/regen_greeting_track.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import Config
from backend.core.incoming_call_audio import greeting_intro_path, greeting_text
from backend.core.incoming_call_settings import (
    apply_incoming_call_settings,
    load_incoming_call_settings,
)
from backend.core.call_manager import CallManager
from backend.database import database as db_module
from backend.voice.ivr_cache import ivr_content_hash


async def main() -> int:
    """Force la regeneration complete du cache accueil."""
    config = Config()
    config.base_path = ROOT
    settings = load_incoming_call_settings(config)
    apply_incoming_call_settings(config, settings)

    ivr_dir = ROOT / "ivr_wav"
    removed = 0
    for pattern in ("voicemail_greeting.*", "greeting_track_*.wav"):
        for path in ivr_dir.glob(pattern):
            path.unlink(missing_ok=True)
            removed += 1
            print(f"supprime: {path.name}")

    await db_module.init_database(config.database_url)
    db = db_module.SessionLocal()
    try:
        cm = CallManager(config, db)
        await cm.voice_synthesis.initialize()
        greeting = greeting_text(config, settings)
        voice = getattr(config, "edge_tts_voice", "?")
        pitch = getattr(config, "edge_tts_pitch", "?")
        rate = getattr(config, "edge_tts_rate", "?")
        h = ivr_content_hash(greeting, cm.voice_synthesis.engine, voice, rate, pitch)
        print(f"TTS: voix={voice} pitch={pitch} rate={rate} hash={h}")
        print(f"texte: {greeting!r}")

        await cm._warmup_ivr_cache()
        audio = cm._audio_settings()
        intro = greeting_intro_path(config, audio)
        print(f"piste: {intro}")
        track = cm._resolve_early_greeting_wav_path()
        print(f"track cache: {track}")
        cm._refresh_early_greeting_wav()
        if track and track.is_file():
            print(f"OK -> {track} ({track.stat().st_size} octets)")
            return 0
        print("ERREUR: track non genere", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
