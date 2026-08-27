"""
Normalisation / filtrage du Caller ID modem (NMBR= / NAME=).

Les operateurs envoient souvent O / P / PRIVATE pour un numero masque ;
il ne faut pas les stocker comme un faux numero.
"""

from __future__ import annotations

from typing import Optional

# Valeurs CID "masque / indisponible" (USR / FR / US).
MASKED_CID_TOKENS = frozenset(
    {
        "O",
        "P",
        "PRIVATE",
        "OUT_OF_AREA",
        "UNAVAILABLE",
        "WITHHELD",
        "ANONYMOUS",
        "UNKNOWN",
        "NOT AVAILABLE",
        "NONDISPONIBLE",
    }
)


def is_masked_cid_token(value: Optional[str]) -> bool:
    """
    Indique si la valeur modem est un masquage, pas un numero / nom utile.

    @param value Texte brut NMBR= ou NAME=.
    @returns True si a ignorer.
    """
    if value is None:
        return True
    cleaned = str(value).strip().strip('"').strip("'")
    if not cleaned:
        return True
    return cleaned.upper() in MASKED_CID_TOKENS


def normalize_cid_value(value: Optional[str]) -> Optional[str]:
    """
    Nettoie une valeur CID ; renvoie None si masquee ou vide.

    @param value Texte brut.
    @returns Valeur exploitable ou None.
    """
    if value is None:
        return None
    cleaned = str(value).strip().strip('"').strip("'")
    if not cleaned or is_masked_cid_token(cleaned):
        return None
    return cleaned


def classify_cid_outcome(
    *,
    caller_id: Optional[str],
    source: str,
    timed_out: bool = False,
) -> str:
    """
    Cause courte pour les logs (timeout / masque / ata / ok / pending).

    @param caller_id Numero retenu (deja normalise).
    @param source Origine (ring / ata / pending).
    @param timed_out True si la fenetre d'attente a expire.
    @returns Code cause.
    """
    if caller_id:
        return "ok" if source != "ata" else "ata"
    if timed_out:
        return "timeout"
    if source == "masque":
        return "masque"
    return "absent"
