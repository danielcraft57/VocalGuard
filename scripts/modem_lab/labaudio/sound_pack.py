#!/usr/bin/env python3
"""
Genere un pack de fichiers audio "special modem".

Sorties:
- version ecoute (WAV 16-bit, 16 kHz)
- version modem (WAV 8-bit unsigned, 8 kHz mono)
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Dict

import sys
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audio_utils import export_wav_8k_8bit


# Presets de voix utiles (decommente/choisis celle que tu preferes):
# fr-FR-DeniseNeural
# fr-FR-HenriNeural
# fr-CA-SylvieNeural
# fr-CA-JeanNeural
DEFAULT_VOICE = "fr-FR-DeniseNeural"

PROMPTS: Dict[str, str] = {
    "welcome": "Bonjour, vous etes sur VocalGuard.",
    "menu_main": "Pour joindre le support, tapez un. Pour le service commercial, tapez deux. Pour laisser un message, tapez trois.",
    "invalid": "Je n'ai pas compris votre choix. Veuillez reessayer.",
    "confirm_1": "Vous avez choisi l'option un.",
    "confirm_2": "Vous avez choisi l'option deux.",
    "confirm_3": "Vous avez choisi l'option trois.",
    "busy": "Tous nos agents sont occupes. Merci de patienter.",
    "goodbye": "Merci pour votre appel. Au revoir.",
    "dtmf_test": "Test clavier. Tapez une touche maintenant.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generation de sons modem via edge-tts")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Voix edge-tts (ex: fr-FR-DeniseNeural)")
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "scripts" / "modem_lab" / "generated"),
        help="Dossier de sortie",
    )
    parser.add_argument(
        "--pack-name",
        default="default",
        help="Nom du sous-dossier du pack (ex: denise_fr, henri_test).",
    )
    parser.add_argument(
        "--prompts-file",
        default=None,
        help="JSON custom {\"id\":\"texte\"} pour remplacer les prompts par defaut.",
    )
    return parser.parse_args()


async def generate_mp3(voice: str, text: str, out_mp3: Path) -> None:
    import edge_tts

    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(out_mp3))


async def run() -> int:
    args = parse_args()
    logger.debug("Args sound_pack: {}", args)
    out_dir = Path(args.out_dir) / args.pack_name
    listen_dir = out_dir / "listen_wav"
    modem_dir = out_dir / "modem_wav"
    mp3_dir = out_dir / "mp3"
    listen_dir.mkdir(parents=True, exist_ok=True)
    modem_dir.mkdir(parents=True, exist_ok=True)
    mp3_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error("pydub non installe")
        print("pydub non installe. Installez: pip install pydub")
        return 1

    prompts = PROMPTS
    if args.prompts_file:
        p = Path(args.prompts_file)
        if not p.exists():
            logger.error("prompts file introuvable: {}", p)
            print(f"prompts file introuvable: {p}")
            return 2
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data:
            logger.error("prompts file invalide: {}", p)
            print("prompts file invalide: attendu objet JSON non vide")
            return 2
        prompts = {str(k): str(v) for k, v in data.items()}
        logger.info("Prompts custom charges: {} entree(s)", len(prompts))

    logger.info("Generation pack '{}' avec voix {}", args.pack_name, args.voice)
    generated = 0
    for name, text in prompts.items():
        mp3_path = mp3_dir / f"{name}.mp3"
        listen_path = listen_dir / f"{name}.wav"
        modem_path = modem_dir / f"{name}.wav"

        await generate_mp3(args.voice, text, mp3_path)
        logger.debug("MP3 genere: {}", mp3_path)
        audio = AudioSegment.from_file(str(mp3_path))
        audio.set_channels(1).set_frame_rate(16000).set_sample_width(2).export(
            str(listen_path), format="wav"
        )
        export_wav_8k_8bit(audio, modem_path)
        logger.info("Prompt '{}' converti -> {}", name, modem_path)

        print(f"[OK] {name}: {modem_path}")
        generated += 1

    print(f"\nGeneration terminee: {generated} prompt(s)")
    print(f"- Ecoute: {listen_dir}")
    print(f"- Modem : {modem_dir}")
    logger.info("Generation terminee: {} prompt(s)", generated)
    return 0

