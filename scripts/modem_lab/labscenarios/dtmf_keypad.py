#!/usr/bin/env python3
"""
Clavier DTMF autonome.

Le scénario peut:
- composer un numéro (optionnel),
- puis envoyer des touches DTMF en direct depuis le clavier PC.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

# Permet d'executer ce script directement depuis la racine du depot.
_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.bootstrap import add_modem_args, build_modem, setup_logging


def parse_args() -> argparse.Namespace:
    """Arguments CLI du clavier DTMF."""
    parser = argparse.ArgumentParser(description="Clavier DTMF (appel sortant optionnel)")
    add_modem_args(parser, need_number=False)
    parser.add_argument("--number", default=None, help="Numero a appeler avant le mode clavier")
    return parser.parse_args()


async def run() -> int:
    """
    Exécute le mode clavier DTMF.

    Codes de retour:
    - 0: succès / sortie utilisateur
    - 1: init modem KO
    - 2: échec composition préalable
    """
    args = parse_args()
    logger.debug("Args dtmf_keypad: {}", args)
    modem = build_modem(args)
    allowed = set("0123456789*#ABCD")
    try:
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1

        if args.number:
            logger.info("Composition du numero {}", args.number)
            ok, raw = await modem.dial_number(args.number)
            logger.info("Dial {} -> ok={} raw={}", args.number, ok, raw or "(vide)")
            if not ok:
                logger.warning("Echec composition avant mode clavier")
                return 2

        print("Mode clavier DTMF: 0-9 * # A-D, h raccroche, q quitte")
        logger.info("Mode clavier DTMF actif")
        while True:
            cmd = (await asyncio.to_thread(input, "keys > ")).strip().upper()
            if not cmd:
                continue
            if cmd in {"Q", "QUIT"}:
                logger.info("Sortie demandee (q)")
                break
            if cmd in {"H", "HANGUP"}:
                logger.info("Raccrochage demande (h)")
                await modem.hangup()
                break
            for ch in cmd:
                if ch not in allowed:
                    print(f"ignore: {ch}")
                    logger.warning("Caractere ignore: {}", ch)
                    continue
                ok = await modem.send_dtmf(ch)
                print(f"{ch}: {'OK' if ok else 'KO'}")
                logger.debug("DTMF {} -> {}", ch, ok)
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        logger.debug("Finalisation dtmf_keypad")
        try:
            await modem.hangup()
        except Exception:
            logger.debug("Raccrochage final ignore (exception)")
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("dtmf_keypad")
    raise SystemExit(asyncio.run(run()))

