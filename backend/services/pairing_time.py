"""Horodatage UTC naif pour les sessions d appairage mobile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def utc_now_naive() -> datetime:
    """
    Instant UTC sans tzinfo (compatible colonnes DateTime naives).

    @returns Datetime UTC naive.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def is_pairing_expired(expires_at: Optional[datetime]) -> bool:
    """
    Indique si une session QR est expiree.

    @param expires_at Date d expiration stockee (naive ou aware).
    @returns True si expiree.
    """
    if expires_at is None:
        return True
    exp = expires_at
    tzinfo = getattr(exp, "tzinfo", None)
    if tzinfo is not None:
        exp = exp.astimezone(timezone.utc).replace(tzinfo=None)
    return exp < utc_now_naive()
