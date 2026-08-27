"""
Normalisation et detection des numeros d appelants.
"""

from __future__ import annotations

from typing import Optional

# Libelles / placeholders jamais consideres comme un vrai numero.
_UNIDENTIFIED_PHONES = frozenset(
    {
        "",
        "inconnu",
        "unknown",
        "anonymous",
        "private",
        "out_of_area",
        "o",
        "p",
        "unavailable",
        "restricted",
    }
)


def normalize_phone_label(phone_number: Optional[str]) -> Optional[str]:
    """
    Nettoie un label numero (trim). Retourne None si vide.

    @param phone_number Valeur brute modem / UI.
    @returns Label nettoye ou None.
    """
    if phone_number is None:
        return None
    cleaned = str(phone_number).strip()
    return cleaned or None


def is_unidentified_phone(phone_number: Optional[str]) -> bool:
    """
    Indique si le numero n est pas identifiable (NULL, vide, O/P, inconnu...).

    @param phone_number Numero stocke sur Call / Caller.
    @returns True si a purger / ne pas lier a un Caller.
    """
    cleaned = normalize_phone_label(phone_number)
    if cleaned is None:
        return True
    compact = cleaned.lower().replace(" ", "")
    if compact in _UNIDENTIFIED_PHONES:
        return True
    # Au moins 3 chiffres : numéros courts FR (ex. 15, 17, 3699) + mobiles / fixes.
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    return len(digits) < 3
