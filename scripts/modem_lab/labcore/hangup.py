#!/usr/bin/env python3
import asyncio

from loguru import logger


async def turbo_hangup(
    modem,
    *,
    enable_console_beep: bool = True,
    cmd_timeout: float = 0.20,
) -> tuple[bool, int]:
    """
    Raccrochage agressif et rapide reutilisable par les scenarios modem_lab.

    Retourne (succes, cycles_utilises).
    """
    stop_beep = asyncio.Event()

    async def _hangup_beep_loop() -> None:
        if not enable_console_beep:
            return
        while not stop_beep.is_set():
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            await asyncio.sleep(0.20)

    beep_task = asyncio.create_task(_hangup_beep_loop(), name="hangup_beep_loop")
    try:
        cycles = 1
        logger.warning("Tentative de raccrochage forcee #{} (turbo)", cycles)
        got_ok = False
        got_no_carrier = False
        for cmd in ("AT+VLS=0", "AT+FCLASS=0", "ATH", "ATH0", "AT+CHUP", "ATH"):
            try:
                raw = await modem.send_command_full(cmd, timeout=cmd_timeout, stop_on_ring=False)
                # Certaines implémentations modem renvoient des caractères non imprimables (ex. "⌂")
                # qui polluent complètement le terminal. On logge une forme compacte.
                text = raw.decode("utf-8", errors="ignore")
                has_ok = "OK" in text
                has_nc = "NO CARRIER" in text
                logger.info(
                    "Hangup sequence {} -> ok={} no_carrier={} ({} octets)",
                    cmd,
                    has_ok,
                    has_nc,
                    len(raw),
                )
                if b"NO CARRIER" in raw:
                    got_no_carrier = True
                if b"OK" in raw:
                    got_ok = True
                    if cmd in {"ATH", "ATH0", "AT+CHUP"}:
                        break
            except Exception as e:
                logger.debug("Hangup sequence {} erreur: {}", cmd, e)
            await asyncio.sleep(0.01)

        if modem.serial_connection and modem.serial_connection.is_open:
            try:
                modem.serial_connection.dtr = False
                await asyncio.sleep(0.08)
                modem.serial_connection.dtr = True
                await asyncio.sleep(0.03)
            except Exception as e:
                logger.debug("Impulsion DTR impossible: {}", e)

        if got_no_carrier:
            logger.info("NO CARRIER detecte, ligne coupee")
            return True, cycles
        if got_ok:
            logger.warning("Validation raccrochage turbo par OK (mobile)")
            return True, cycles
        return False, cycles
    finally:
        stop_beep.set()
        beep_task.cancel()
        try:
            await beep_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
