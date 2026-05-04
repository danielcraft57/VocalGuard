#!/usr/bin/env python3
"""
Scénario répondeur (TAD) pour modem voix.

Fonctions principales:
- décroché automatique sur appel entrant,
- lecture d'un message d'accueil WAV,
- bip simple/double configurable,
- enregistrement du message correspondant,
- raccrochage robuste.
"""
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
import math
import tempfile
import wave

from loguru import logger

# Permet d'executer ce script directement depuis la racine du depot.
_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.answer import fast_answer_incoming
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.hangup import turbo_hangup
from labcore.voice_line import play_wav_line_fallback


def parse_args() -> argparse.Namespace:
    """Arguments CLI du scénario répondeur."""
    parser = argparse.ArgumentParser(description="Repondeur modem (auto answer + message + enregistrement)")
    add_modem_args(parser, need_number=False)
    parser.add_argument("--answer-delay-ms", type=int, default=0, help="Delai avant decrochage auto (ms)")
    parser.add_argument(
        "--greeting-wav",
        default=None,
        help="WAV d'accueil a jouer (8 kHz mono recommande)",
    )
    parser.add_argument("--record-seconds", type=float, default=25.0, help="Duree enregistrement message (s)")
    parser.add_argument("--beep", action="store_true", help="Jouer un bip avant l'enregistrement")
    parser.add_argument("--beep-ms", type=int, default=300, help="Duree du bip (ms)")
    parser.add_argument("--beep-hz", type=int, default=1000, help="Frequence du bip (Hz)")
    parser.add_argument(
        "--beep-pattern",
        choices=["single", "double"],
        default="single",
        help="Pattern du bip: single (classique) ou double (pro).",
    )
    parser.add_argument("--beep2-ms", type=int, default=150, help="Duree du 2e bip (ms), pattern double")
    parser.add_argument("--beep2-hz", type=int, default=780, help="Frequence du 2e bip (Hz), pattern double")
    parser.add_argument(
        "--record-timeout-extra-sec",
        type=float,
        default=5.0,
        help="Marge de timeout additionnelle pour l'enregistrement (s)",
    )
    parser.add_argument(
        "--record-dir",
        default=str(Path(__file__).resolve().parents[1] / "generated" / "voicemail"),
        help="Dossier de sortie des messages",
    )
    return parser.parse_args()


def _write_u8_wav(path: Path, raw_u8: bytes, rate: int = 8000) -> None:
    """Écrit un flux PCM u8 mono dans un conteneur WAV."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(rate)
        wf.writeframes(raw_u8)


def _generate_beep_u8(duration_ms: int, hz: int, level: float = 0.8) -> bytes:
    """Génère un bip sinusoïdal PCM u8 (8 kHz)."""
    rate = 8000
    n_samples = max(1, int(rate * duration_ms / 1000))
    out = bytearray(n_samples)
    for i in range(n_samples):
        s = math.sin(2.0 * math.pi * hz * (i / rate))
        out[i] = max(0, min(255, 128 + int(127 * level * s)))
    return bytes(out)


def _enforce_wav_duration(path: Path, target_seconds: float) -> None:
    """Ajuste un WAV à une durée cible (padding/troncature)."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    bytes_per_frame = max(1, channels * sampwidth)
    target_frames = max(1, int(framerate * target_seconds))
    target_bytes = target_frames * bytes_per_frame
    current = len(frames)
    if current < target_bytes:
        # Complete avec du silence pour garantir la duree demandee.
        silence_val = b"\x80" if sampwidth == 1 else b"\x00"
        frames = frames + silence_val * (target_bytes - current)
    elif current > target_bytes:
        frames = frames[:target_bytes]
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(frames)


async def run() -> int:
    """
    Exécute le scénario répondeur.

    Codes de retour:
    - 0: succès / interruption volontaire
    - 1: init modem KO
    - 2: échec décroché
    - 3: échec lecture greeting
    - 4: échec enregistrement
    """
    args = parse_args()
    logger.debug("Args answering_machine: {}", args)
    modem = build_modem(args)
    # ring_event: synchronisation callback RING -> boucle run().
    ring_event = asyncio.Event()
    latest_caller_id = "-"
    monitor_task = None
    hangup_done = False
    last_hangup_attempts = 0

    async def on_incoming_call(**kwargs):
        nonlocal latest_caller_id
        caller_id = kwargs.get("caller_id")
        if caller_id:
            latest_caller_id = str(caller_id)
        ring_event.set()

    modem.on_incoming_call = on_incoming_call

    async def _record_with_fallback(duration_sec: float, out_path: Path) -> bool:
        # Meme logique que pour la lecture: forcer la sequence complete d'abord.
        ok = await modem.record_wav_via_serial(
            duration_sec,
            out_path,
            already_in_voice_mode=False,
        )
        if ok:
            return True
        # Fallback secondaire: tentative en mode courant.
        logger.warning("Enregistrement sequence complete KO, retry en mode courant")
        return await modem.record_wav_via_serial(
            duration_sec,
            out_path,
            already_in_voice_mode=True,
        )

    async def _stop_monitor() -> None:
        nonlocal monitor_task
        modem.is_initialized = False
        if monitor_task is not None:
            try:
                monitor_task.cancel()
                await monitor_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            monitor_task = None

    try:
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1
        monitor_task = asyncio.create_task(modem.monitor_calls(), name="monitor_calls")
        logger.info("Repondeur en attente d'un appel entrant...")
        await ring_event.wait()
        logger.info("RING detecte (caller_id={})", latest_caller_id)

        delay = max(0, args.answer_delay_ms) / 1000.0
        if delay:
            await asyncio.sleep(delay)

        ok, cid, name = await fast_answer_incoming(modem, ata_attempts=6, ata_timeout=0.1, sleep_between=0.15)
        logger.info("answer_call(fast) -> ok={} cid={} name={}", ok, cid or "-", name or "-")
        if not ok:
            logger.error("Impossible de decrocher l'appel entrant")
            return 2

        greeting = Path(args.greeting_wav) if args.greeting_wav else None
        if greeting:
            if not greeting.exists():
                logger.error("Message d'accueil introuvable: {}", greeting)
                return 3
            logger.info("Lecture message d'accueil: {}", greeting)
            played = await play_wav_line_fallback(modem, greeting)
            if not played:
                logger.warning("Lecture message d'accueil echouee")
            await asyncio.sleep(0.2)

        if args.beep:
            logger.info(
                "Emission bip d'enregistrement (pattern={}, b1={}ms@{}Hz, b2={}ms@{}Hz)",
                args.beep_pattern,
                args.beep_ms,
                args.beep_hz,
                args.beep2_ms,
                args.beep2_hz,
            )
            with tempfile.NamedTemporaryFile(prefix="beep_", suffix=".wav", delete=False) as tmp:
                beep_path = Path(tmp.name)
            try:
                beep = _generate_beep_u8(max(60, int(args.beep_ms)), max(200, int(args.beep_hz)))
                if args.beep_pattern == "double":
                    beep += bytes([128]) * int(8000 * 0.08)
                    beep += _generate_beep_u8(max(60, int(args.beep2_ms)), max(200, int(args.beep2_hz)))
                beep += bytes([128]) * int(8000 * 0.1)  # petite pause apres bip(s)
                _write_u8_wav(beep_path, beep, rate=8000)
                played_beep = await play_wav_line_fallback(modem, beep_path)
                if not played_beep:
                    logger.warning("Bip non joue (echec VTX)")
            finally:
                try:
                    beep_path.unlink(missing_ok=True)
                except Exception:
                    pass

        rec_dir = Path(args.record_dir)
        rec_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_cid = (cid or latest_caller_id or "unknown").replace(" ", "_")
        rec_path = rec_dir / f"msg_{safe_cid}_{stamp}.wav"
        logger.info("Enregistrement message vers {} ({} s)", rec_path, args.record_seconds)
        rec_seconds = max(1.0, float(args.record_seconds))
        timeout_sec = rec_seconds + max(1.0, float(args.record_timeout_extra_sec))
        try:
            recorded = await asyncio.wait_for(
                _record_with_fallback(rec_seconds, rec_path),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.error("Timeout enregistrement apres {:.1f}s", timeout_sec)
            recorded = False
        if not recorded:
            logger.warning("Enregistrement du message echoue")
            await _stop_monitor()
            ok_hang, attempts = await turbo_hangup(modem, enable_console_beep=True)
            last_hangup_attempts = attempts
            hangup_done = True
            logger.info("Raccrochage repondeur apres echec enregistrement -> {}", ok_hang)
            return 4
        _enforce_wav_duration(rec_path, rec_seconds)
        logger.info("Duree fichier normalisee a {} s", rec_seconds)

        logger.info("Message enregistre: {}", rec_path)
        await _stop_monitor()
        ok_hang, attempts = await turbo_hangup(modem, enable_console_beep=True)
        last_hangup_attempts = attempts
        hangup_done = True
        logger.info("Raccrochage repondeur -> {}", ok_hang)
        print(f"[Hangup] cycles utilises: {last_hangup_attempts} | succes={ok_hang}")
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        await _stop_monitor()
        try:
            if not hangup_done:
                ok_hang, attempts = await turbo_hangup(modem, enable_console_beep=True)
                last_hangup_attempts = attempts
                logger.debug("Raccrochage final finally -> {}", ok_hang)
                print(f"[Hangup] cycles utilises: {last_hangup_attempts} | succes={ok_hang}")
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("answering_machine")
    raise SystemExit(asyncio.run(run()))
