#!/usr/bin/env python3
"""
Test modem : decrocher un appel, jouer un fichier WAV, enregistrer un message repondeur.

En mode voix serie (modem Conexant) : lecture et enregistrement passent par le port serie
(VTX pour jouer, VRX pour enregistrer). Sinon ALSA (aplay/arecord) si le modem expose une carte son.
A lancer sur le Raspberry Pi avec le modem connecte (ex. pi@raspberrypi.local).

Usage:
  cd ~/VocalGuard && source venv/bin/activate
  python scripts/test_modem_answer_play_record.py
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from backend.core.config import Config
from backend.core.modem_handler import ModemHandler


# Duree d'enregistrement du message (secondes)
RECORD_DURATION = 30
# Fichier WAV a jouer apres decrochage (message type "laissez un message apres le bip")
DEFAULT_WAV = PROJECT_ROOT / "ivr_wav" / "ivr_message.wav"
# Repertoire de sortie des messages enregistres
RECORDINGS_DIR = PROJECT_ROOT / "recordings"
# Methode de lecture WAV : "serial" = mode voix sur le port serie (comme callattendant, modem Conexant),
# "alsa" = aplay sur le peripherique ALSA du modem. Si USE_MODEM_VOICE_MODE=1 on force "serial".
USE_VOICE_SERIAL = os.environ.get("USE_MODEM_VOICE_MODE", "").strip() in ("1", "true", "yes")
# Peripherique ALSA (utilise seulement si lecture par ALSA)
ALSA_MODEM_PLAY = os.environ.get("ALSA_MODEM_DEVICE") or os.environ.get("ALSA_DEVICE", "default")
ALSA_MODEM_RECORD = os.environ.get("ALSA_MODEM_RECORD_DEVICE") or ALSA_MODEM_PLAY


async def play_wav_to_line(wav_path: Path, alsa_device: str) -> bool:
    """
    Joue un fichier WAV sur le modem (vers la ligne telephonique).
    L'appelant entend ce qui est joue sur ce peripherique ALSA.

    Args:
        wav_path: Chemin du fichier WAV.
        alsa_device: Peripherique ALSA du modem (ex. hw:1,0).

    Returns:
        True si la lecture a reussi.
    """
    if not wav_path or not wav_path.exists():
        logger.error("Fichier WAV introuvable: {}", wav_path)
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "aplay",
            "-D", alsa_device,
            "-q",
            str(wav_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("aplay a retourne {}: {}", proc.returncode, stderr.decode(errors="ignore"))
            return False
        logger.info("Lecture WAV terminee: {}", wav_path.name)
        return True
    except FileNotFoundError:
        logger.error("aplay introuvable. Installez alsa-utils: sudo apt-get install alsa-utils")
        return False
    except Exception as e:
        logger.exception("Erreur lecture WAV: {}", e)
        return False


async def record_from_line(
    duration_sec: int,
    out_path: Path,
    alsa_device: str,
    rate: int = 8000,
) -> bool:
    """
    Enregistre l'audio depuis la ligne telephonique (modem) via arecord.

    Args:
        duration_sec: Duree en secondes.
        out_path: Fichier de sortie WAV.
        alsa_device: Device ALSA.
        rate: Taux d'echantillonnage (8000 Hz telephone).

    Returns:
        True si l'enregistrement a reussi.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "arecord",
            "-D", alsa_device,
            "-d", str(duration_sec),
            "-f", "S16_LE",
            "-r", str(rate),
            "-c", "1",
            "-q",
            str(out_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("arecord a retourne {}: {}", proc.returncode, stderr.decode(errors="ignore"))
            return False
        logger.info("Enregistrement sauve: {}", out_path)
        return True
    except FileNotFoundError:
        logger.error("arecord introuvable. Installez alsa-utils: sudo apt-get install alsa-utils")
        return False
    except Exception as e:
        logger.exception("Erreur enregistrement: {}", e)
        return False


async def on_incoming_call(modem: ModemHandler, config: dict):
    """
    Callback appele a chaque RING : decroche, joue le WAV, enregistre le message, raccroche.

    config: dict avec wav_path, record_duration, alsa_play, alsa_record, recordings_dir.
    """
    logger.info("Appel entrant detecte: decrochage...")
    ok, _cid, _cname = await modem.answer_call()
    if not ok:
        logger.error("Impossible de decrocher")
        return

    wav_path = config.get("wav_path") or DEFAULT_WAV
    record_duration = config.get("record_duration") or RECORD_DURATION
    use_serial = config.get("use_voice_serial")
    alsa_play = config.get("alsa_play") or ALSA_MODEM_PLAY
    alsa_record = config.get("alsa_record") or ALSA_MODEM_RECORD
    recordings_dir = config.get("recordings_dir") or RECORDINGS_DIR

    try:
        if use_serial:
            logger.info("Lecture WAV sur le modem (mode voix, port serie)...")
            ok = await modem.play_wav_via_serial(wav_path, already_in_voice_mode=True)
            if not ok:
                logger.warning("Echec lecture WAV via serie, pas de fallback ALSA dans ce script.")
        else:
            logger.info("Lecture WAV sur le modem (ALSA)...")
            ok = await play_wav_to_line(wav_path, alsa_play)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = recordings_dir / f"voicemail_{timestamp}.wav"
        if use_serial:
            logger.info("Enregistrement message depuis la ligne (mode voix, port serie VRX)...")
            recorded = await modem.record_wav_via_serial(
                float(record_duration), out_file, already_in_voice_mode=True
            )
        else:
            logger.info("Enregistrement message depuis le modem (ALSA)...")
            recorded = await record_from_line(record_duration, out_file, alsa_record)
        if not recorded:
            logger.warning(
                "Enregistrement non effectue (VRX echoue ou device ALSA invalide). "
                "En mode serie, verifiez les logs modem. En ALSA: arecord -L et ALSA_MODEM_RECORD_DEVICE."
            )
    finally:
        await modem.hangup()
        logger.info("Appel termine, raccroche.")


async def main():
    """Boucle principale : initialise le modem et surveille les appels."""
    logger.info("Test modem: decrocher -> jouer WAV (ligne telephone) -> enregistrer message")
    logger.info("Fichier WAV: {}", DEFAULT_WAV)
    logger.info("Duree enregistrement: {} s", RECORD_DURATION)
    logger.info("Sortie messages: {}", RECORDINGS_DIR)

    config = Config(config_path=PROJECT_ROOT / "config" / "config.yaml")
    if not (PROJECT_ROOT / "config" / "config.yaml").exists():
        config_path_alt = PROJECT_ROOT / "config.yaml"
        if config_path_alt.exists():
            config.load_from_yaml(config_path_alt)
    modem = ModemHandler(config.modem_port, config.modem_baudrate)
    initialized = await modem.initialize()
    if not initialized:
        logger.error("Modem non initialise. Verifiez le port (modem_port) et le cable.")
        sys.exit(1)

    # Préférer le mode voix série (port série) si le modem est Conexant ou si forcé par env
    use_voice_serial = USE_VOICE_SERIAL or modem.supports_voice_serial
    if use_voice_serial:
        logger.info("Lecture WAV: mode voix port serie (comme callattendant)")
    else:
        logger.info("Lecture WAV: ALSA (device {}). Pour forcer le mode serie: export USE_MODEM_VOICE_MODE=1", ALSA_MODEM_PLAY)
        if ALSA_MODEM_PLAY == "default":
            logger.warning("Si l'appelant n'entend pas le WAV, faites 'aplay -l' puis export ALSA_MODEM_DEVICE=hw:X,0")

    run_config = {
        "wav_path": DEFAULT_WAV,
        "record_duration": RECORD_DURATION,
        "use_voice_serial": use_voice_serial,
        "alsa_play": ALSA_MODEM_PLAY,
        "alsa_record": ALSA_MODEM_RECORD,
        "recordings_dir": RECORDINGS_DIR,
    }

    async def callback(caller_id=None, caller_name=None):
        await on_incoming_call(modem, run_config)

    modem.on_incoming_call = callback
    logger.info("En attente d'appels... (Ctrl+C pour quitter)")
    try:
        await modem.monitor_calls()
    except KeyboardInterrupt:
        logger.info("Arret demande")
    finally:
        modem.close()


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    asyncio.run(main())
