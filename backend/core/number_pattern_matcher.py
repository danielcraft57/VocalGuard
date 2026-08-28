"""
Correspondance de numeros / masques CID pour la policy incoming_call.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.core.incoming_call_types import (
    IncomingNumberPatternRule,
    IncomingProfileName,
)


_MASKED_VALUES = frozenset({"P", "O", "PRIVATE", "UNKNOWN", "ANONYMOUS", "UNAVAILABLE"})


def normalize_cid_for_pattern(caller_id: Optional[str]) -> str:
    """
    Normalise un CID pour comparaison pattern.

    @param caller_id Numero ou masque.
    @returns Chaine upper strippee.
    """
    if not caller_id:
        return ""
    return str(caller_id).strip().upper()


def match_pattern_rule(caller_id: Optional[str], rule: IncomingNumberPatternRule) -> bool:
    """
    Teste si un numero correspond a une regle.

    Formats supportes :
    - ``P`` / ``O`` : appels masques
    - prefixe SQL ``+338%``
    - prefixe ``^`` ou suffixe ``$`` : regex Python
    - sinon : egalite ou suffixe numerique

    @param caller_id CID appelant.
    @param rule Regle configuree.
    @returns True si match.
    """
    if not rule.enabled:
        return False
    pat = (rule.pattern or "").strip()
    if not pat:
        return False
    cid = normalize_cid_for_pattern(caller_id)
    if not cid:
        return False

    if pat.upper() in ("P", "O", "MASKED", "ANONYMOUS"):
        return cid in _MASKED_VALUES

    if pat.endswith("%"):
        return cid.startswith(pat[:-1].upper())

    if pat.startswith("^") or pat.endswith("$") or ".*" in pat:
        try:
            return bool(re.search(pat, cid, re.IGNORECASE))
        except re.error:
            return False

    pat_up = pat.upper()
    if cid == pat_up:
        return True
    digits = "".join(ch for ch in cid if ch.isdigit())
    pat_digits = "".join(ch for ch in pat_up if ch.isdigit())
    if pat_digits and digits.endswith(pat_digits):
        return True
    return cid.endswith(pat_up.lstrip("+"))


def match_number_pattern_profile(
    caller_id: Optional[str],
    rules: list[IncomingNumberPatternRule],
    *,
    enabled: bool = True,
) -> Optional[IncomingProfileName]:
    """
    Premiere regle correspondante gagne.

    @param caller_id Numero appelant.
    @param rules Liste ordonnee de regles.
    @param enabled Feature activee.
    @returns Profil force ou None.
    """
    if not enabled or not caller_id:
        return None
    for rule in rules:
        if match_pattern_rule(caller_id, rule):
            return rule.action
    return None
