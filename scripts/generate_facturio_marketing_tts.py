#!/usr/bin/env python3
"""
Genere les pistes voix TTS pour la publicite Facturio (reels, LinkedIn, Shorts).

Base sur le pipeline VocalGuard (edge-tts + pydub), alimente par :
  data/marketing/facturio-publicite-2026.json

Usage :
  python scripts/generate_facturio_marketing_tts.py
  python scripts/generate_facturio_marketing_tts.py --variant 30s-main --voice fr-FR-HenriNeural
  python scripts/generate_facturio_marketing_tts.py --list-voices
  python scripts/generate_facturio_marketing_tts.py --variant all --format mp3 --concat-full

Sortie par defaut :
  data/marketing/tts-output/facturio/<variant_id>/
    segment_01-hook.mp3
    ...
    full.mp3          (si --concat-full)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = PROJECT_ROOT / "data" / "marketing" / "facturio-publicite-2026.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "marketing" / "tts-output" / "facturio"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def _load_payload(json_path: Path) -> dict[str, Any]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def _select_variants(payload: dict[str, Any], variant_arg: str) -> List[dict[str, Any]]:
    variants = payload.get("variants") or []
    if variant_arg == "all":
        return variants
    for v in variants:
        if v.get("id") == variant_arg:
            return [v]
    ids = ", ".join(v.get("id", "?") for v in variants)
    raise SystemExit(f"Variante inconnue: {variant_arg!r}. Disponibles: {ids}")


async def _list_voices(locale_filter: Optional[str] = "fr") -> None:
    try:
        import edge_tts
    except ImportError:
        raise SystemExit("Installez edge-tts: pip install edge-tts")

    voices = await edge_tts.list_voices()
    if locale_filter:
        voices = [v for v in voices if (v.get("Locale") or "").lower().startswith(locale_filter.lower())]
    voices = sorted(voices, key=lambda v: (v.get("Locale", ""), v.get("ShortName", "")))
    print(f"\n--- Voix edge-tts ({len(voices)}) ---")
    print(f"{'ShortName':<32}  {'Gender':<8}  Locale")
    print("-" * 56)
    for v in voices:
        print(f"{(v.get('ShortName') or ''):<32}  {(v.get('Gender') or ''):<8}  {v.get('Locale') or ''}")
    print()


async def _tts_edge_to_file(text: str, voice: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(str(out_path))


def _export_segment(segment_path: Path, out_path: Path, fmt: str) -> None:
    from pydub import AudioSegment

    audio = AudioSegment.from_file(str(segment_path))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "mp3":
        audio.export(str(out_path), format="mp3", bitrate="192k")
    elif fmt == "wav":
        audio.export(str(out_path), format="wav")
    else:
        raise ValueError(f"Format non supporte: {fmt}")


def _concat_segments(
    parts: Iterable[Path],
    out_path: Path,
    pause_ms: int,
    fmt: str,
) -> None:
    from pydub import AudioSegment

    combined: AudioSegment | None = None
    silence = AudioSegment.silent(duration=max(0, pause_ms))
    for part in parts:
        chunk = AudioSegment.from_file(str(part))
        combined = chunk if combined is None else combined + silence + chunk
    if combined is None:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "mp3":
        combined.export(str(out_path), format="mp3", bitrate="192k")
    else:
        combined.export(str(out_path), format="wav")


async def _generate_variant(
    variant: dict[str, Any],
    *,
    voice: str,
    output_root: Path,
    fmt: str,
    force: bool,
    concat_full: bool,
    pause_ms: int,
) -> int:
    variant_id = variant.get("id") or "variant"
    label = variant.get("label") or variant_id
    segments = variant.get("segments") or []
    target_dir = output_root / variant_id
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n-> {variant_id} — {label}")
    generated = 0
    segment_files: List[Path] = []

    with tempfile.TemporaryDirectory(prefix="vg_facturio_tts_") as tmp_dir:
        tmp = Path(tmp_dir)
        for seg in segments:
            seg_id = seg.get("id") or f"seg_{generated + 1:02d}"
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            out_file = target_dir / f"segment_{seg_id}.{fmt}"
            segment_files.append(out_file)
            if out_file.exists() and not force:
                print(f"  skip: {out_file.name}")
                continue
            raw = tmp / f"{seg_id}.mp3"
            await _tts_edge_to_file(text, voice, raw)
            _export_segment(raw, out_file, fmt)
            print(f"  ok  : {out_file.name}")
            generated += 1

        if concat_full and segment_files:
            full_path = target_dir / f"full.{fmt}"
            existing = [p for p in segment_files if p.exists()]
            if existing and (force or not full_path.exists()):
                # Re-gen temp chunks for concat if skipped above
                concat_parts: List[Path] = []
                for seg in segments:
                    text = (seg.get("text") or "").strip()
                    if not text:
                        continue
                    seg_id = seg.get("id") or "seg"
                    part = tmp / f"concat_{seg_id}.mp3"
                    if not part.exists():
                        await _tts_edge_to_file(text, voice, part)
                    concat_parts.append(part)
                _concat_segments(concat_parts, full_path, pause_ms, fmt)
                print(f"  ok  : {full_path.name} (concat {len(concat_parts)} segments)")
                generated += 1

    return generated


async def run(args: argparse.Namespace) -> int:
    if args.list_voices:
        await _list_voices(args.locale)
        return 0

    json_path = Path(args.input)
    if not json_path.is_file():
        raise SystemExit(f"Fichier introuvable: {json_path}")

    payload = _load_payload(json_path)
    meta = payload.get("meta") or {}
    voice = args.voice or meta.get("default_voice") or "fr-FR-DeniseNeural"
    pause_ms = args.pause_ms if args.pause_ms is not None else int(meta.get("pause_between_segments_ms") or 450)
    output_root = Path(args.output)

    try:
        from pydub import AudioSegment  # noqa: F401
    except ImportError:
        raise SystemExit("Installez pydub (+ ffmpeg): pip install pydub")

    variants = _select_variants(payload, args.variant)
    print(f"Script: {meta.get('title', 'Facturio marketing')}")
    print(f"Voix: {voice} | Format: {args.format} | Sortie: {output_root}")

    total = 0
    for variant in variants:
        total += await _generate_variant(
            variant,
            voice=voice,
            output_root=output_root,
            fmt=args.format,
            force=args.force,
            concat_full=args.concat_full,
            pause_ms=pause_ms,
        )

    print(f"\nGeneration terminee: {total} fichier(s).")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TTS publicite Facturio (edge-tts).")
    parser.add_argument(
        "--input",
        default=str(DEFAULT_JSON),
        help="JSON marketing (segments + variantes)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Dossier de sortie",
    )
    parser.add_argument(
        "--variant",
        default="30s-main",
        help="ID variante ou 'all' (30s-main, 15s-teaser, ab-urgence, ab-metier)",
    )
    parser.add_argument("--voice", default=None, help="Voix edge-tts (ex. fr-FR-DeniseNeural)")
    parser.add_argument("--format", choices=["mp3", "wav"], default="mp3", help="Format de sortie")
    parser.add_argument("--pause-ms", type=int, default=None, help="Pause entre segments (concat full)")
    parser.add_argument("--concat-full", action="store_true", help="Generer full.mp3 par variante")
    parser.add_argument("--force", action="store_true", help="Regenerer meme si le fichier existe")
    parser.add_argument("--list-voices", action="store_true", help="Lister les voix FR edge-tts")
    parser.add_argument("--locale", default="fr", help="Filtre locale pour --list-voices")
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    try:
        raise SystemExit(asyncio.run(run(arguments)))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
