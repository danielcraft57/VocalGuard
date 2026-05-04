#!/usr/bin/env python3
"""
CLI unifiée pour lancer tous les scénarios modem_lab.

Conception
----------
- une seule commande d'entrée (`cli.py`)
- un sous-commande par scénario (`dialer`, `incoming`, `outbound-announce`, ...)
- les arguments restants sont transmis tels quels au script cible

Exemple
-------
`python scripts/modem_lab/cli.py dialer -- --port COM6 --number 147`

Voir aussi ``labscenarios/README.md`` (rôles des scénarios, sonde vs répondeur entrant/sortant).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent

# Table de routage: nom public de la sous-commande -> script Python réel.
SCENARIO_MAP = {
    "smoke": LAB_DIR / "labscenarios" / "smoke_tests.py",
    "dialer": LAB_DIR / "labscenarios" / "dialer.py",
    "outgoing": LAB_DIR / "labscenarios" / "outgoing_call.py",
    "incoming": LAB_DIR / "labscenarios" / "incoming_call.py",
    "dtmf": LAB_DIR / "labscenarios" / "dtmf_keypad.py",
    "answering": LAB_DIR / "labscenarios" / "answering_machine.py",
    "outbound-announce": LAB_DIR / "labscenarios" / "outbound_announce.py",
    "outbound-listen-vad": LAB_DIR / "labscenarios" / "outbound_listen_vad.py",
    "prompt-and-play": LAB_DIR / "labscenarios" / "prompt_and_play.py",
    "answer-metrics-probe": LAB_DIR / "labscenarios" / "answer_metrics_probe.py",
    "answer-vosk-live-probe": LAB_DIR / "labscenarios" / "answer_vosk_live_probe.py",
    "metrics-voicemail": LAB_DIR / "labscenarios" / "metrics_voicemail.py",
    "prospection-outbound": LAB_DIR / "labscenarios" / "prospection_outbound.py",
}


def build_parser() -> argparse.ArgumentParser:
    """Construit le parser de la CLI racine."""
    epilog = """
Scénarios (détail : scripts/modem_lab/labscenarios/README.md) :
  answer-metrics-probe   Sonde VRX : métriques + capture.wav + rapport timing.
  answer-vosk-live-probe Compose + STT Vosk live (partials/finals) + transcript.srt en continu.
  metrics-voicemail      Sonde puis prompt WAV, bips, message répondeur (sortant).
  prospection-outbound   Sonde + greeting + STT Vosk (SUB/VTT) + réponse intent optionnelle.
  smoke                    Fumée AT / modem prêt.
  dialer                   Compose, maintient la ligne, raccroche.
  outgoing                 Compose puis DTMF interactif (clavier).
  outbound-announce        Compose, attentes, lecture WAV vers la ligne.
  outbound-listen-vad      VRX + VAD sans WAV (logs parole).
  incoming                 Attente RING, décrochage, pont audio.
  answering                Répondeur entrant (greeting + enregistrement).
  dtmf                     DTMF sur ligne établie.
  prompt-and-play          Séquences audio / touches (avancé).
"""

    parser = argparse.ArgumentParser(
        description="CLI unifiée modem_lab (dispatch vers scripts labscenarios/*).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog.strip(),
    )
    parser.add_argument(
        "scenario",
        choices=sorted(SCENARIO_MAP.keys()),
        help="Scénario à exécuter.",
    )
    parser.add_argument(
        "scenario_args",
        nargs=argparse.REMAINDER,
        help="Arguments transmis tels quels au scénario cible (préfixer avec --).",
    )
    return parser


def build_command(ns: argparse.Namespace) -> list[str]:
    """
    Construit la commande finale à exécuter.

    Le séparateur ``--`` est optionnel; s'il est présent il est retiré avant dispatch.
    """
    target = SCENARIO_MAP[ns.scenario]
    tail = list(ns.scenario_args)
    if tail and tail[0] == "--":
        tail = tail[1:]
    return [sys.executable, str(target), *tail]


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée testable: parse puis exécute le scénario demandé."""
    ns = build_parser().parse_args(argv)
    cmd = build_command(ns)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

