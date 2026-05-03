#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from labcore.bootstrap import setup_logging
from labaudio.tts_engine import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Menu TTS modem_lab")
    parser.add_argument(
        "--selection-file",
        default=None,
        help="Fichier ou sauvegarder la voix choisie.",
    )
    parser.add_argument(
        "--initial-voice",
        default=None,
        help="Voix preselectionnee au demarrage.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    setup_logging("tts_engine")
    args = parse_args()
    selection_file = Path(args.selection_file) if args.selection_file else None
    asyncio.run(run(selection_file=selection_file, initial_voice=args.initial_voice))
