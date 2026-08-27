"""
Branchement unique du relais telephony sur le bus d'evenements (idempotent par processus).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from loguru import logger

if TYPE_CHECKING:
    from backend.core.config import Config
    from backend.telephony_daemon.relay import PublicApiEventRelay

_wired: bool = False
_relay_instance: Optional["PublicApiEventRelay"] = None


def wire_daemon_relay_once(config: "Config") -> "PublicApiEventRelay":
    """
    Abonne PublicApiEventRelay au bus global une seule fois (evite les doublons au reload).

    @param config Configuration daemon.
    @returns Instance de relais (partagee).
    """
    global _wired, _relay_instance
    from backend.telephony_daemon.relay import PublicApiEventRelay

    if _wired and _relay_instance is not None:
        return _relay_instance
    from backend.core.events import event_bus

    _relay_instance = PublicApiEventRelay.from_config(config)
    if not _wired:
        event_bus.subscribe_all(_relay_instance)
        _wired = True
        logger.debug("Telephony daemon: relais evenements branche sur event_bus")
    return _relay_instance


def get_wired_relay() -> Optional["PublicApiEventRelay"]:
    """Retourne le relais courant (si branche)."""
    return _relay_instance
