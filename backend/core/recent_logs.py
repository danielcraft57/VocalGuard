"""
Tampon memoire des derniers logs (affiche dans l'UI, sans ouvrir le terminal).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Deque, Dict, List

_MAX = 80
_lines: Deque[Dict[str, str]] = deque(maxlen=_MAX)


def push_recent_log(level: str, message: str) -> None:
    """
    Ajoute une ligne au journal recent.

    @param level INFO | WARNING | ERROR.
    @param message Texte court.
    """
    _lines.append(
        {
            "at": datetime.utcnow().strftime("%H:%M:%S"),
            "level": (level or "INFO")[:16],
            "message": (message or "")[:800],
        }
    )


def recent_logs(limit: int = 40) -> List[Dict[str, str]]:
    """
    Dernieres lignes, de la plus ancienne a la plus recente.

    @param limit Nombre max.
    """
    items = list(_lines)
    if limit <= 0:
        return []
    return items[-limit:]
