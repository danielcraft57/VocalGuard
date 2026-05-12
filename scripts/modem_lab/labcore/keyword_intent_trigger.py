#!/usr/bin/env python3
"""
Déclencheurs simples (keyword spotting) sur texte STT.

But: automatiser des enchaînements "quand on entend X -> jouer Y" sans aller vers un module ML.
Sur un PC, Vosk suffit souvent pour un premier pipeline stable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize_fr_text(s: str) -> str:
    """Normalisation légère: minuscules + suppression accents + espaces propres."""
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s


@dataclass(frozen=True)
class KeywordTrigger:
    pattern: str
    tag: str
    once: bool = True

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern, flags=re.IGNORECASE)


class KeywordIntentTrigger:
    """
    Déclenche un intent quand une phrase finale matche un pattern.

    - "once" (défaut): ne déclenche qu'une fois par tag.
    """

    def __init__(self, triggers: list[KeywordTrigger]) -> None:
        self._compiled: list[tuple[KeywordTrigger, re.Pattern[str]]] = [(t, t.compile()) for t in triggers]
        self._fired: set[str] = set()

    def consider_final(self, text: str) -> list[str]:
        """Retourne la liste des tags déclenchés par ce texte final."""
        norm = normalize_fr_text(text)
        if not norm:
            return []
        out: list[str] = []
        for trig, rx in self._compiled:
            if trig.once and trig.tag in self._fired:
                continue
            if rx.search(norm):
                out.append(trig.tag)
                if trig.once:
                    self._fired.add(trig.tag)
        return out

