#!/usr/bin/env python3
"""
Scénario d'appel sortant interactif orienté DTMF.

Après composition, l'utilisateur pilote les touches DTMF depuis le clavier PC
et peut raccrocher à la demande.
"""

import argparse
import asyncio

from loguru import logger

from labcore.bootstrap import add_modem_args, build_modem, setup_logging


def parse_args() -> argparse.Namespace:
    """Arguments CLI minimaux: port/baud/numéro à composer."""
    parser = argparse.ArgumentParser(description="Appel sortant interactif")
    add_modem_args(parser, need_number=True)
    return parser.parse_args()


async def interactive_dtmf(modem) -> None:
    """Boucle interactive clavier -> DTMF modem jusqu'à sortie utilisateur."""
    logger.debug("Entree dans la boucle interactive DTMF")
    print("Commandes: chiffres/*/#/A-D pour DTMF, h pour raccrocher, q pour quitter")
    allowed = set("0123456789*#ABCD")
    while True:
        cmd = (await asyncio.to_thread(input, "DTMF/h/q > ")).strip().upper()
        if not cmd:
            continue
        if cmd in {"Q", "QUIT"}:
            logger.info("Sortie demandee par utilisateur (q)")
            break
        if cmd in {"H", "HANGUP"}:
            logger.info("Raccrochage demande (h)")
            await modem.hangup()
            break
        sent = False
        for ch in cmd:
            if ch not in allowed:
                logger.warning("Caractere DTMF ignore: {}", ch)
                continue
            ok = await modem.send_dtmf(ch)
            print(f"{ch}: {'OK' if ok else 'KO'}")
            logger.debug("DTMF {} -> {}", ch, ok)
            sent = True
        if not sent:
            print("Aucune touche valide.")


async def run() -> int:
    """
    Exécute le scénario sortant interactif.

    Codes de retour:
    - 0: succès / interruption volontaire
    - 1: init modem KO
    - 2: composition KO
    """
    args = parse_args()
    logger.debug("Args outgoing_call: {}", args)
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
            logger.warning("Echec composition")
            return 2
        logger.info("Appel etabli/en cours, passage en mode interactif")
        await interactive_dtmf(modem)
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        logger.debug("Finalisation outgoing_call")
        try:
            await modem.hangup()
        except Exception:
            logger.debug("Raccrochage final ignore (exception)")
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("outgoing_call")
    raise SystemExit(asyncio.run(run()))

