#!/usr/bin/env python3
"""
Retranscrit les messages vocaux sans transcription (STT Vosk/Whisper).

Usage (sur le Pi, depuis /opt/vocalguard) :
  venv/bin/python scripts/retranscribe_voicemails.py
  venv/bin/python scripts/retranscribe_voicemails.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio

import backend.database.database as db_module
from backend.api.routes.voicemails import _resolve_voicemail_audio
from backend.core.config import Config
from backend.database.models import Voicemail
from backend.services.call_service import CallService
from backend.voice.audio_utils import load_wav_as_16k16bit_pcm
from backend.voice.recognition import VoiceRecognition

async def _run(limit: int) -> int:
    config = Config()
    await db_module.init_database(config.database_url)
    if db_module.SessionLocal is None:
        raise SystemExit("Base de donnees non initialisee.")
    recognition = VoiceRecognition(config)
    await recognition.initialize()
    if recognition.engine not in ("whisper", "vosk"):
        raise SystemExit("STT indisponible (Vosk/Whisper non charge).")

    db = db_module.SessionLocal()
    try:
        rows = (
            db.query(Voicemail)
            .filter((Voicemail.transcription.is_(None)) | (Voicemail.transcription == ""))
            .order_by(Voicemail.created_at.desc())
            .limit(limit)
            .all()
        )
        if not rows:
            print("Aucun message a retranscrire.")
            return 0
        call_service = CallService(db)
        done = 0
        for vm in rows:
            path = _resolve_voicemail_audio(config, vm.audio_file or "")
            if path is None:
                print(f"#{vm.id}: fichier introuvable ({vm.audio_file})")
                continue
            try:
                pcm = load_wav_as_16k16bit_pcm(path)
            except (OSError, ValueError, ImportError) as exc:
                print(f"#{vm.id}: {exc}")
                continue
            text = (await recognition.transcribe(pcm, sample_rate=16000) or "").strip()
            if not text:
                print(f"#{vm.id}: STT vide")
                continue
            await call_service.set_voicemail_transcription(vm.id, text)
            print(f"#{vm.id}: {text[:120]}")
            done += 1
        print(f"Termine: {done}/{len(rows)} message(s) retranscrit(s).")
        return done
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Retranscription STT des messages vocaux.")
    parser.add_argument("--limit", type=int, default=20, help="Nombre max de messages a traiter.")
    args = parser.parse_args()
    asyncio.run(_run(args.limit))


if __name__ == "__main__":
    main()
