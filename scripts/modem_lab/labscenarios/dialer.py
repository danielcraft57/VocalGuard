#!/usr/bin/env python3
import argparse
import asyncio

from loguru import logger

from labcore.bootstrap import add_modem_args, build_modem, setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Numerotation simple via modem")
    add_modem_args(parser, need_number=True)
    parser.add_argument("--hold-seconds", type=float, default=8.0, help="Duree avant raccrochage")
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    logger.debug("Args dialer: {}", args)
    modem = build_modem(args)
    try:
        logger.info("Initialisation modem en cours...")
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1
        logger.info("Composition du numero {}", args.number)
        ok, raw = await modem.dial_number(args.number)
        logger.info("Dial {} -> ok={} raw={}", args.number, ok, raw or "(vide)")
        if not ok:
            logger.warning("Composition non confirmee, fin du scenario dialer")
            return 2
        logger.debug("Attente de {} seconde(s) avant raccrochage", max(0.0, args.hold_seconds))
        await asyncio.sleep(max(0.0, args.hold_seconds))
        await modem.hangup()
        logger.info("Raccrochage effectue")
        return 0
    finally:
        logger.debug("Fermeture modem")
        modem.close()


if __name__ == "__main__":
    setup_logging("dialer")
    raise SystemExit(asyncio.run(run()))

