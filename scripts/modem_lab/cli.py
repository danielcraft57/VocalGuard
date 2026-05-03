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
}


def build_parser() -> argparse.ArgumentParser:
    """Construit le parser de la CLI racine."""
    parser = argparse.ArgumentParser(
        description="CLI unifiée modem_lab (dispatch vers scripts labscenarios/*)."
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

