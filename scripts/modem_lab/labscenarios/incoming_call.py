#!/usr/bin/env python3
"""
Scénario d'appel entrant avec pont audio PC <-> ligne.

Flux général:
1) attente de RING via ``monitor_calls``
2) décroché auto (ou manuel)
3) ouverture VRX puis démarrage ``LiveAudioBridge``
4) boucle interactive utilisateur (raccrocher, quitter, push-to-talk)

Ce scénario est utile pour valider rapidement la chaîne voix en conditions réelles.
"""

import argparse
import asyncio

from loguru import logger

from labcore.answer import fast_answer_incoming
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.live_audio import LiveAudioBridge


def parse_args() -> argparse.Namespace:
    """Arguments CLI du scénario entrant (décroché + audio live)."""
    parser = argparse.ArgumentParser(description="Attente appel entrant + decrochage")
    add_modem_args(parser, need_number=False)
    parser.add_argument(
        "--auto-answer",
        dest="auto_answer",
        action="store_true",
        help="Decroche automatiquement des le premier RING (defaut).",
    )
    parser.add_argument(
        "--manual-answer",
        dest="auto_answer",
        action="store_false",
        help="Mode manuel: attendre 'a' pour decrocher.",
    )
    parser.add_argument(
        "--answer-delay-ms",
        type=int,
        default=0,
        help="Delai avant decrochage auto (ms).",
    )
    parser.add_argument("--input-device", type=int, default=None, help="Index device micro")
    parser.add_argument("--output-device", type=int, default=None, help="Index device haut-parleur")
    parser.add_argument("--uplink-burst-ms", type=int, default=260, help="Taille rafales micro modem")
    parser.add_argument("--rx-only", action="store_true", help="Ecoute uniquement, sans micro")
    parser.add_argument("--push-to-talk", action="store_true", help="Micro actif avec la touche v")
    parser.add_argument("--ptt-ms", type=int, default=1200, help="Duree push-to-talk (ms)")
    parser.set_defaults(auto_answer=True)
    return parser.parse_args()


async def run() -> int:
    """
    Exécute le scénario entrant.

    Codes de retour:
    - 0: succès / sortie utilisateur
    - 1: échec initialisation modem
    """
    args = parse_args()
    logger.debug("Args incoming_call: {}", args)
    modem = build_modem(args)
    # ring_event synchronise la détection d'appel entre callback modem et boucle run().
    ring_event = asyncio.Event()
    # latest_caller_id est la dernière valeur observée dans les événements entrants.
    latest_caller_id = "-"

    async def on_incoming_call(**kwargs):
        """Callback modem appelé à chaque RING / notification entrante."""
        nonlocal latest_caller_id
        caller_id = kwargs.get("caller_id")
        if caller_id:
            latest_caller_id = str(caller_id)
        ring_event.set()
        logger.debug("Event ring recu (caller_id={})", latest_caller_id)

    modem.on_incoming_call = on_incoming_call
    monitor_task = None
    bridge = None
    vrx_opened = False
    try:
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1
        monitor_task = asyncio.create_task(modem.monitor_calls(), name="monitor_calls")
        logger.info("En attente d'un appel entrant...")
        await ring_event.wait()
        logger.info("RING detecte (caller_id={})", latest_caller_id)

        if args.auto_answer:
            delay = max(0, args.answer_delay_ms) / 1000.0
            if delay:
                logger.debug("Delai auto-answer: {} ms", args.answer_delay_ms)
                await asyncio.sleep(delay)
            ok, cid, name = await fast_answer_incoming(modem)
            logger.info("answer_call(auto) -> ok={} cid={} name={}", ok, cid or "-", name or "-")
            if not ok:
                logger.error("Echec decrochage auto")
                print("Echec decrochage auto. Passe en mode manuel.")
            else:
                print("Appel pris en auto. Tape 'h' pour raccrocher.")
        else:
            print("RING detecte. Tape 'a' pour decrocher, 'q' pour quitter.")
            while True:
                cmd = (await asyncio.to_thread(input, "a/q > ")).strip().lower()
                if cmd == "q":
                    logger.info("Sortie manuelle avant decrochage")
                    return 0
                if cmd == "a":
                    ok, cid, name = await fast_answer_incoming(modem)
                    logger.info("answer_call -> ok={} cid={} name={}", ok, cid or "-", name or "-")
                    break
            print("Appel pris. Tape 'h' pour raccrocher.")

        vrx_opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=True)
        if not vrx_opened:
            logger.error("Impossible d'ouvrir le flux audio VRX apres decrochage")
        else:
            bridge = LiveAudioBridge(
                modem=modem,
                input_device_index=args.input_device,
                output_device_index=args.output_device,
                uplink_burst_ms=args.uplink_burst_ms,
                rx_only=args.rx_only,
                push_to_talk=args.push_to_talk,
            )
            if await bridge.start():
                logger.info("Audio live entrant actif")
                print("Audio actif. Commandes: h raccrocher, q quitter, v push-to-talk")
            else:
                logger.warning("Audio live indisponible, appel sans pont audio")

        while True:
            cmd = (await asyncio.to_thread(input, "h/q/v > ")).strip().lower()
            if cmd == "h":
                await modem.hangup()
                logger.info("Raccrochage effectue")
                return 0
            if cmd == "q":
                return 0
            if cmd == "v" and bridge is not None and args.push_to_talk and not args.rx_only:
                await bridge.push_to_talk_once(args.ptt_ms)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        logger.debug("Finalisation incoming_call")
        if bridge is not None:
            await bridge.stop()
        if vrx_opened:
            try:
                await modem.end_outgoing_vrx_stream()
            except Exception:
                logger.debug("Fermeture VRX ignoree (exception)")
        modem.is_initialized = False
        if monitor_task is not None:
            try:
                monitor_task.cancel()
            except Exception:
                logger.debug("Annulation monitor_task ignoree (exception)")
                pass
        modem.close()


if __name__ == "__main__":
    setup_logging("incoming_call")
    raise SystemExit(asyncio.run(run()))

