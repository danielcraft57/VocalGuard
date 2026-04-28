#!/usr/bin/env python3
"""
Utilitaires partages pour les scripts de tests vocaux.
"""

import asyncio
import os
import subprocess
import sys
import wave
from pathlib import Path

from loguru import logger


def setup_logging() -> None:
    """Configure un logging lisible pour les tests CLI."""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )


def check_rpi_voice_engine() -> None:
    """Sur Raspberry Pi, recommande VOSK pour eviter les soucis d'instructions CPU."""
    if os.environ.get("VOICE_RECOGNITION_ENGINE", "").lower() == "vosk":
        return
    try:
        with open("/proc/device-tree/model", "r", encoding="utf-8") as f:
            if "Raspberry" in (f.read() or ""):
                logger.warning(
                    "Sur Raspberry Pi, utilisez Vosk: VOICE_RECOGNITION_ENGINE=vosk."
                )
    except Exception:
        pass


def check_sounddevice() -> None:
    """Verifie que sounddevice est bien disponible."""
    try:
        import sounddevice as sd

        sd.query_devices()
    except Exception as exc:
        logger.error(f"sounddevice indisponible: {exc}")
        sys.exit(1)


async def play_audio_file(audio_file: Path) -> None:
    """Lit un fichier audio en essayant d'abord la methode native de l'OS."""
    if not audio_file or not audio_file.exists():
        logger.warning(f"Fichier audio introuvable: {audio_file}")
        return

    if sys.platform.startswith("linux"):
        try:
            duration = 3.0
            try:
                with wave.open(str(audio_file), "rb") as wf:
                    duration = wf.getnframes() / float(wf.getframerate())
            except Exception:
                pass
            subprocess.run(["aplay", "-D", "default", str(audio_file)], check=True, timeout=int(duration) + 5)
            return
        except Exception:
            pass

    if sys.platform == "win32" and audio_file.suffix.lower() == ".wav":
        try:
            import winsound

            winsound.PlaySound(str(audio_file), winsound.SND_FILENAME | winsound.SND_ASYNC)
            await asyncio.sleep(2.0)
            return
        except Exception:
            pass

    try:
        import pygame

        pygame.mixer.init()
        pygame.mixer.music.load(str(audio_file))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        pygame.mixer.quit()
    except Exception as exc:
        logger.warning(f"Lecture audio indisponible: {exc}")

