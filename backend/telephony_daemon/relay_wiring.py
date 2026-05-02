"""
Branchement unique du relais telephony sur le bus d'evenements (idempotent par processus).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from backend.core.config import Config

_wired: bool = False


def wire_daemon_relay_once(config: "Config") -> None:
    """
    Abonne PublicApiEventRelay au bus global une seule fois (evite les doublons au reload).
    """
    global _wired
    if _wired:
        return
    from backend.core.events import event_bus
    from backend.telephony_daemon.relay import PublicApiEventRelay

    event_bus.subscribe_all(PublicApiEventRelay.from_config(config))
    _wired = True
    logger.debug("Telephony daemon: relais evenements branche sur event_bus")
