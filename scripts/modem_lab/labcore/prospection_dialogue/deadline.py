"""
**Budget temps wall-clock** pour un segment d’appel (pattern *Deadline* / compte à rebours).

Intérêt
--------
- Les tours STT utilisent ``listen_sec`` chacun ; sans plafond global, un ``dialogue_max_turns``
  élevé peut dépasser le temps acceptable sur la ligne.
- ``CallDeadline`` borne la durée **réelle** (``time.monotonic``) : on peut raccourcir le dernier
  ``pump`` Vosk pour finir avant la coupure réseau ou la politique métier.

Variables (``CallDeadline``)
---------------------------
- ``_end_monotonic`` : instant absolu de fin ; comparé à ``time.monotonic()`` (immunisé aux ajustements d’horloge).
"""

from __future__ import annotations

import time


class CallDeadline:
    """
    Compte à rebours monotonic : ``expired()`` devient vrai après ``budget_sec`` secondes **réelles**.

    ``budget_sec`` doit être > 0. Utiliser ``remaining_sec()`` pour tronquer une écoute STT
    (``min(listen_sec, remaining)``).
    """

    __slots__ = ("_end_monotonic",)

    def __init__(self, budget_sec: float) -> None:
        if budget_sec <= 0.0:
            raise ValueError("budget_sec doit être strictement positif")
        self._end_monotonic: float = time.monotonic() + float(budget_sec)

    def expired(self) -> bool:
        """Vrai si le budget est épuisé (ou égal, tolérance 0)."""
        return time.monotonic() >= self._end_monotonic

    def remaining_sec(self) -> float:
        """Secondes restantes avant ``expired()`` (0.0 si dépassé)."""
        return max(0.0, self._end_monotonic - time.monotonic())
