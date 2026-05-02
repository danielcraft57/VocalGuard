"""
Relais des evenements du bus local vers l'API publique (POST /internal/telephony-events).

Implémentation dédiée au processus telephony : une seule responsabilité, testable sans modem.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from backend.core.events import Event

if TYPE_CHECKING:
    from backend.core.config import Config


def _relay_warn_interval_sec() -> float:
    try:
        return float(os.environ.get("TELEPHONY_RELAY_WARN_INTERVAL_SEC", "30").strip() or "30")
    except ValueError:
        return 30.0


class PublicApiEventRelay:
    """
    Handler async compatible avec event_bus.subscribe_all : relaie chaque Event vers l'API principale.
    """

    __slots__ = ("_base", "_token", "_last_warn_ts", "_skipped_since_warn")

    def __init__(self, public_api_base_url: str, internal_token: str) -> None:
        self._base = public_api_base_url.rstrip("/")
        self._token = internal_token.strip()
        self._last_warn_ts = 0.0
        self._skipped_since_warn = 0

    @classmethod
    def from_config(cls, config: "Config") -> PublicApiEventRelay:
        base = (getattr(config, "telephony_public_api_url", None) or "http://127.0.0.1:8000").rstrip("/")
        token = (getattr(config, "telephony_internal_token", None) or "").strip()
        return cls(base, token)

    async def __call__(self, event: Event) -> None:
        if not self._token:
            logger.debug("telephony relay: pas de TELEPHONY_INTERNAL_TOKEN, skip")
            return
        payload = {
            "event_type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "source": event.source,
        }
        url = f"{self._base}/api/v1/internal/telephony-events"
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    url,
                    json=payload,
                    headers={"X-VocalGuard-Internal": self._token},
                    timeout=10.0,
                )
            if r.status_code >= 400:
                self._throttled_warning(
                    "telephony relay HTTP {}: {}",
                    r.status_code,
                    r.text[:200],
                )
        except Exception as exc:
            self._throttled_warning("telephony relay echec: {}", exc)

    def _throttled_warning(self, fmt: str, *args: object) -> None:
        """Evite de saturer les logs (ex. transcription partielle => dizaines d events/s si l API est hors ligne)."""
        now = time.monotonic()
        interval = _relay_warn_interval_sec()
        if now - self._last_warn_ts >= interval:
            suffix = ""
            if self._skipped_since_warn:
                suffix = f" ({self._skipped_since_warn} echecs relays non journalises depuis dernier log)"
                self._skipped_since_warn = 0
            logger.warning(fmt + suffix, *args)
            self._last_warn_ts = now
        else:
            self._skipped_since_warn += 1


def make_relay_handler(config: "Config"):
    """Compat : retourne une coroutine liee (meme contrat que l'ancien event_relay)."""
    relay = PublicApiEventRelay.from_config(config)
    return relay
