#!/usr/bin/env python3
"""
Scénario de smoke tests AT.

But: vérifier rapidement que le modem répond à un noyau minimal de commandes
avant d'exécuter des scénarios voix plus complexes.
"""

import argparse
import asyncio

from loguru import logger

from labcore.bootstrap import add_modem_args, build_modem, setup_logging


def parse_args() -> argparse.Namespace:
    """Arguments CLI des tests de fumée."""
    parser = argparse.ArgumentParser(description="Smoke tests modem (AT de base)")
    add_modem_args(parser, need_number=False)
    return parser.parse_args()


def _ok(resp: bytes) -> bool:
    """Retourne True si la réponse AT contient OK."""
    return b"OK" in resp


async def run() -> int:
    """
    Exécute la batterie courte de commandes AT.

    Codes de retour:
    - 0: tous les tests OK
    - 1: initialisation modem KO
    - 2: au moins un test KO
    """
    args = parse_args()
    logger.debug("Args smoke_tests: {}", args)
    modem = build_modem(args)
    results: list[tuple[str, bool, str]] = []
    try:
        logger.info("Demarrage smoke tests modem")
        init_ok = await modem.initialize()
        results.append(("initialize", init_ok, "init modem"))
        if not init_ok:
            logger.error("Init modem KO")
            for name, ok, detail in results:
                print(f"[{'OK' if ok else 'KO'}] {name}: {detail}")
            return 1

        tests = [
            ("AT", "AT"),
            ("ATE0", "ATE0"),
            ("ATI", "ATI"),
            ("FCLASS8", "AT+FCLASS=8"),
            ("VSM", "AT+VSM=128,8000"),
            ("VTD", "AT+VTD=10"),
        ]
        for name, command in tests:
            try:
                logger.debug("Test {} -> {}", name, command)
                resp = await modem.send_command_full(command, timeout=3.0, stop_on_ring=False)
                text = resp.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
                results.append((name, _ok(resp), text or "(vide)"))
            except Exception as e:
                logger.exception("Erreur test {}: {}", name, e)
                results.append((name, False, str(e)))

        for name, ok, detail in results:
            print(f"[{'OK' if ok else 'KO'}] {name}: {detail}")
        all_ok = all(ok for _, ok, _ in results)
        if all_ok:
            logger.info("Smoke tests OK")
            return 0
        logger.warning("Smoke tests avec echec(s)")
        return 2
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        logger.debug("Finalisation smoke_tests")
        try:
            await modem.hangup()
        except Exception:
            logger.debug("Raccrochage final ignore (exception)")
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("smoke_tests")
    raise SystemExit(asyncio.run(run()))

