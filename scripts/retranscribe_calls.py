#!/usr/bin/env python3
"""
Retranscrit des appels et leurs messages vocaux lies (STT Vosk).

Usage sur node15 :
  cd /opt/vocalguard
  set -a && . .env && set +a
  PYTHONPATH=/opt/vocalguard venv/bin/python scripts/retranscribe_calls.py 8 9
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import backend.database.database as db_module
from backend.api.routes.voicemails import _resolve_voicemail_audio
from backend.core.config import Config
from backend.database.models import Call, Voicemail
from backend.services.call_service import CallService
from backend.voice.audio_utils import load_wav_as_16k16bit_pcm
from backend.voice.recognition import VoiceRecognition


def _resolve_recording(config: Config, audio_file: str) -> Path | None:
    """Resout un WAV d'appel (recordings/...)."""
    if not audio_file or ".." in audio_file:
        return None
    base = Path(config.base_path) if config.base_path else Path.cwd()
    candidate = (base / audio_file.replace("\\", "/").lstrip("/")).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


async def _transcribe_file(recognition: VoiceRecognition, path: Path) -> tuple[str, int, list]:
    """Transcrit un fichier WAV, retourne (texte, octets PCM, cues)."""
    pcm = load_wav_as_16k16bit_pcm(path)
    text, cues = await recognition.transcribe_with_cues(pcm, sample_rate=16000)
    return (text or "").strip(), len(pcm), cues or []


async def _run(call_ids: list[int]) -> None:
    config = Config()
    await db_module.init_database(config.database_url)
    if db_module.SessionLocal is None:
        raise SystemExit("Base non initialisee.")

    recognition = VoiceRecognition(config)
    await recognition.initialize()
    if recognition.engine not in ("whisper", "vosk"):
        raise SystemExit("STT indisponible.")

    engine = recognition.engine
    model = config.vosk_model_path or config.whisper_model
    print(f"Moteur STT: {engine} ({model})")
    print("=" * 60)

    db = db_module.SessionLocal()
    try:
        call_service = CallService(db)
        for call_id in call_ids:
            call = db.query(Call).filter(Call.id == call_id).first()
            if call is None:
                print(f"Appel #{call_id}: introuvable")
                continue

            vm = db.query(Voicemail).filter(Voicemail.call_id == call_id).order_by(Voicemail.id.desc()).first()
            old_call_tx = (call.transcription or "").strip() or None
            old_vm_tx = (vm.transcription or "").strip() if vm else None

            print(f"\n### Appel #{call_id}")
            print(f"  Date      : {call.call_time}")
            print(f"  Duree     : {call.duration}s" if call.duration else "  Duree     : ?")
            print(f"  Numero    : {call.phone_number or '(inconnu)'}")
            print(f"  Statut    : {call.status}")
            if vm:
                print(f"  Voicemail : #{vm.id} ({vm.duration}s)")

            # Transcription enregistrement appel complet
            rec_path = _resolve_recording(config, call.audio_file or "")
            if rec_path:
                print(f"  Audio appel : {rec_path.name} ({rec_path.stat().st_size // 1024} Ko)")
                try:
                    new_call_tx, pcm_len, cues = await _transcribe_file(recognition, rec_path)
                    print(f"  STT appel   : {new_call_tx or '(vide)'} [{pcm_len} octets PCM]")
                    if new_call_tx:
                        await call_service.set_transcription_and_intent(
                            call_id, transcription=new_call_tx, cues=cues or None
                        )
                except Exception as exc:
                    print(f"  STT appel   : ERREUR {exc}")
                    new_call_tx = None
            else:
                print(f"  Audio appel : absent ({call.audio_file})")
                new_call_tx = None

            # Transcription message vocal
            if vm and vm.audio_file:
                vm_path = _resolve_voicemail_audio(config, vm.audio_file)
                if vm_path:
                    print(f"  Audio VM    : {vm_path.name} ({vm_path.stat().st_size // 1024} Ko)")
                    try:
                        new_vm_tx, pcm_len, _cues = await _transcribe_file(recognition, vm_path)
                        print(f"  STT VM      : {new_vm_tx or '(vide)'} [{pcm_len} octets PCM]")
                        if new_vm_tx:
                            await call_service.set_voicemail_transcription(vm.id, new_vm_tx)
                    except Exception as exc:
                        print(f"  STT VM      : ERREUR {exc}")
                        new_vm_tx = None
                else:
                    print(f"  Audio VM    : introuvable ({vm.audio_file})")
                    new_vm_tx = None
            else:
                new_vm_tx = None

            print("  --- Comparaison ---")
            print(f"  Appel avant : {old_call_tx or '(aucune)'}")
            print(f"  Appel apres : {new_call_tx or '(aucune)'}")
            if vm:
                print(f"  VM avant    : {old_vm_tx or '(aucune)'}")
                print(f"  VM apres    : {new_vm_tx or '(aucune)'}")

        print("\n" + "=" * 60)
        print("Termine.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Retranscription STT appels + messages lies.")
    parser.add_argument("call_ids", nargs="+", type=int, help="IDs appels (ex: 8 9)")
    args = parser.parse_args()
    asyncio.run(_run(args.call_ids))


if __name__ == "__main__":
    main()
