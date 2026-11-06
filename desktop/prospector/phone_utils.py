"""
Normalisation numeros pour match entrant / cache ProspectLab.
"""

from __future__ import annotations

from typing import Optional


def phone_digits(raw: Optional[str]) -> Optional[str]:
    """
    Extrait les chiffres d'un numero ou CID.

    @param raw Valeur brute.
    @returns Chiffres only ou None.
    """
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return digits or None
