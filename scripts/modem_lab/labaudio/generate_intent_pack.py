#!/usr/bin/env python3
"""
CLI : génère des WAV 8 kHz depuis un JSON d’intents (ex. ``data/intents_prospection_flow.json``).

Exemple (depuis la racine du dépôt ; valeurs avec espaces : guillemets) ::
    python scripts/modem_lab/labaudio/generate_intent_pack.py ^
      --intents data/intents_prospection_flow.json ^
      --out scripts/modem_lab/generated/prospection_pack/demo ^
      --voice fr-FR-DeniseNeural ^
      --var agent_name=Alex ^
      --var company_name=MaBoite ^
      --var "value_prop_short=l automatisation" ^
      --var "domain=l'IA" ^
      --var "pain_point=la gestion des appels"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_MODEM_LAB = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB))

from labaudio.intent_wav_pack import (
    build_pack_from_json,
    load_placeholders_json,
    parse_placeholder_args,
)
from labcore.bootstrap import setup_logging


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Génère des WAV modem depuis intents JSON + placeholders.")
    p.add_argument(
        "--intents",
        type=Path,
        required=True,
        help="Fichier JSON (clé intents[].tag / responses[]).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("scripts/modem_lab/generated/prospection_pack/manual"),
        help="Dossier de sortie des WAV.",
    )
    p.add_argument("--voice", default="fr-FR-DeniseNeural", help="Voix edge-tts")
    p.add_argument(
        "--vars-json",
        type=Path,
        default=None,
        help="JSON {\"agent_name\":\"…\", …} pour {{placeholders}}.",
    )
    p.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="Placeholder répétable (prioritaire sur --vars-json en cas de doublon).",
    )
    p.add_argument("--force", action="store_true", help="Régénérer même si le WAV existe.")
    p.add_argument(
        "--album",
        default=None,
        help="Métadonnée « album » (IPRD) ; défaut = dernier segment du dossier --out.",
    )
    return p.parse_args()


async def run(args: argparse.Namespace | None = None) -> int:
    args = args if args is not None else parse_args()
    intents = Path(args.intents)
    if not intents.is_file():
        print(f"Fichier intents introuvable: {intents}", file=sys.stderr)
        return 1

    ph = load_placeholders_json(args.vars_json)
    ph.update(parse_placeholder_args(args.var))

    await build_pack_from_json(
        intents,
        Path(args.out),
        ph,
        voice=str(args.voice),
        force=bool(args.force),
        album=args.album,
    )
    print(f"OK — pack dans {args.out}")
    return 0


if __name__ == "__main__":
    try:
        _cli = parse_args()
    except SystemExit as _e:
        raise SystemExit(_e.code) from None
    setup_logging("generate_intent_pack")
    raise SystemExit(asyncio.run(run(_cli)))
