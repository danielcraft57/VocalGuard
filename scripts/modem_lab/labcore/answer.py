#!/usr/bin/env python3
"""Decrochage entrant reutilisable pour les scenarios modem_lab."""

import asyncio
from typing import Optional, Tuple

from loguru import logger


async def fast_answer_incoming(
    modem,
    *,
    ata_attempts: int = 6,
    ata_timeout: float = 0.1,
    sleep_between: float = 0.15,
) -> Tuple[bool, str, str]:
    """
    Rafale de ATA courte, puis fallback ModemHandler.answer_call.

    Retourne (ok, caller_id, caller_name) ; sur decrochage rapide, id/name sont "-".
    Utiliser l'identifiant vu au RING si besoin (callback on_incoming_call).
    """
    for attempt in range(1, max(1, ata_attempts) + 1):
        try:
            raw = await modem.send_command_full("ATA", timeout=ata_timeout, stop_on_ring=False)
            text = raw.decode("utf-8", errors="ignore").strip().replace("\r\n", " | ")
            logger.info("Fast ATA (tentative {}) -> {}", attempt, text or "(vide)")
            if b"OK" in raw or b"CONNECT" in raw:
                return True, "-", "-"
        except Exception as e:
            logger.debug("Fast ATA tentative {} erreur: {}", attempt, e)
        await asyncio.sleep(max(0.0, sleep_between))
    ok: bool
    cid: Optional[str]
    name: Optional[str]
    ok, cid, name = await modem.answer_call()
    return ok, cid or "-", name or "-"
