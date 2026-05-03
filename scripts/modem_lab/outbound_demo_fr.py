#!/usr/bin/env python3
"""
Appel sortant démo (France) : numéro **0780833873** par défaut, avec les options recommandées
pour mobile / absence de CONNECT données :

  --voice-blind-dial --wait-answer-tone --wait-rings 5 --ring-duration-sec 4

Depuis la racine du dépôt VocalGuard :

  python scripts/modem_lab/outbound_demo_fr.py --message-wav chemin/vers/annonce_8k.wav --port COM6

Arguments supplémentaires sont transmis à ``outbound_announce`` (voir ``python scripts/modem_lab/labscenarios/outbound_announce.py --help``).
"""

import argparse
import asyncio
import sys

from labcore.bootstrap import setup_logging


def _build_argv(ns: argparse.Namespace, passthrough: list[str]) -> None:
    argv = ["outbound_demo_fr"]
    if ns.port:
        argv.extend(["--port", ns.port])
    argv.extend(
        [
            "--baudrate",
            str(ns.baudrate),
            "--number",
            ns.number,
            "--message-wav",
            ns.message_wav,
            "--voice-blind-dial",
            "--wait-answer-tone",
            "--wait-rings",
            str(ns.wait_rings),
            "--ring-duration-sec",
            str(ns.ring_duration_sec),
        ]
    )
    argv.extend(passthrough)
    sys.argv = argv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Appel sortant démo (0780833873, wait-answer-tone, 5×4 s budget sonnerie)",
        add_help=True,
    )
    parser.add_argument("--port", default=None, help="Port série modem (ex. COM6)")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--number",
        default="0780833873",
        help="Numéro à composer (défaut : démo FR)",
    )
    parser.add_argument(
        "--message-wav",
        required=True,
        help="Fichier WAV annonce (8 kHz mono recommandé)",
    )
    parser.add_argument(
        "--wait-rings",
        type=int,
        default=5,
        help="Cycles sonnerie estimés si repli après --wait-answer-tone",
    )
    parser.add_argument(
        "--ring-duration-sec",
        type=float,
        default=4.0,
        help="Durée d'un cycle sonnerie+silence (s)",
    )
    ns, rest = parser.parse_known_args()
    _build_argv(ns, rest)
    setup_logging("outbound_demo_fr")
    from labscenarios.outbound_announce import run

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
