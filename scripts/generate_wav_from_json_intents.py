#!/usr/bin/env python3
"""
Genere des WAV telephoniques (8 kHz, mono, 8-bit) a partir de fichiers intents JSON.

Usage rapide:
  python scripts/generate_wav_from_json_intents.py --glob "data/intents_danielcraft_*.json" --engine edge --voice fr-FR-DeniseNeural
  python scripts/generate_wav_from_json_intents.py --glob "data/*.json" --engine coqui --speaker "Zacharie Aimilios"
"""

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audio_utils import export_wav_8k_8bit


def _resolve_intent_files(glob_pattern: str) -> List[Path]:
    files = sorted(PROJECT_ROOT.glob(glob_pattern))
    return [f for f in files if f.is_file() and f.suffix.lower() == ".json"]


def _safe_name(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in value).strip("_")[:80] or "intent"


def _iter_responses(intent_file: Path) -> Iterable[Tuple[str, str]]:
    payload = json.loads(intent_file.read_text(encoding="utf-8"))
    intents = payload.get("intents") or []
    for idx, item in enumerate(intents):
        tag = item.get("tag") or f"intent_{idx + 1}"
        responses = item.get("responses") or []
        for ridx, response in enumerate(responses):
            text = (response or "").strip()
            if text:
                yield f"{_safe_name(tag)}_{ridx + 1:02d}", text


async def _tts_edge(text: str, voice: str, out_file: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_file))


def _tts_gtts(text: str, lang: str, out_file: Path) -> None:
    from gtts import gTTS

    gTTS(text=text, lang=lang, slow=False).save(str(out_file))


def _tts_coqui(text: str, language: str, speaker: str, model_name: str, out_file: Path) -> None:
    from TTS.api import TTS

    tts = TTS(model_name=model_name, progress_bar=False, gpu=False)
    tts.tts_to_file(text=text, language=language, speaker=speaker, file_path=str(out_file))


async def _generate_one(
    engine: str,
    text: str,
    voice: str,
    lang: str,
    speaker: str,
    model_name: str,
    out_wav: Path,
) -> None:
    from pydub import AudioSegment

    with tempfile.TemporaryDirectory(prefix="vg_tts_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        if engine == "edge":
            temp_audio = tmp_path / "tts.mp3"
            await _tts_edge(text, voice, temp_audio)
        elif engine == "gtts":
            temp_audio = tmp_path / "tts.mp3"
            _tts_gtts(text, lang, temp_audio)
        elif engine == "coqui":
            temp_audio = tmp_path / "tts.wav"
            _tts_coqui(text, lang, speaker, model_name, temp_audio)
        else:
            raise ValueError(f"Moteur non supporte: {engine}")

        segment = AudioSegment.from_file(str(temp_audio))
        export_wav_8k_8bit(segment, out_wav)


async def run(args: argparse.Namespace) -> int:
    files = _resolve_intent_files(args.glob)
    if not files:
        print(f"Aucun fichier trouve pour le glob: {args.glob}")
        return 1

    total = 0
    print(f"Fichiers intents: {len(files)}")
    for intent_file in files:
        target_dir = PROJECT_ROOT / args.output / intent_file.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n-> {intent_file}")
        for base_name, text in _iter_responses(intent_file):
            out_wav = target_dir / f"{base_name}.wav"
            if out_wav.exists() and not args.force:
                print(f"  skip: {out_wav.name}")
                continue
            await _generate_one(
                engine=args.engine,
                text=text,
                voice=args.voice,
                lang=args.lang,
                speaker=args.speaker,
                model_name=args.coqui_model,
                out_wav=out_wav,
            )
            print(f"  ok  : {out_wav.name}")
            total += 1

    print(f"\nGeneration terminee: {total} fichier(s) genere(s).")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genere des WAV 8 kHz depuis des intents JSON.")
    parser.add_argument("--glob", default="data/*.json", help="Glob relatif racine projet (ex: data/intents_*.json)")
    parser.add_argument("--output", default="ivr_wav/generated", help="Dossier de sortie relatif a la racine")
    parser.add_argument("--engine", choices=["edge", "gtts", "coqui"], default="edge", help="Moteur TTS")
    parser.add_argument("--voice", default="fr-FR-DeniseNeural", help="Voix pour edge-tts")
    parser.add_argument("--lang", default="fr", help="Langue (gtts/coqui)")
    parser.add_argument("--speaker", default="Zacharie Aimilios", help="Speaker Coqui XTTS")
    parser.add_argument(
        "--coqui-model",
        default="tts_models/multilingual/multi-dataset/xtts_v2",
        help="Nom du modele Coqui TTS",
    )
    parser.add_argument("--force", action="store_true", help="Regenerer meme si le WAV existe deja")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        raise SystemExit(asyncio.run(run(arguments)))
    except KeyboardInterrupt:
        raise SystemExit(130)
