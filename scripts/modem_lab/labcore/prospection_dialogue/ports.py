"""
**Ports** (interfaces) pour inverser les dépendances (hexagonal / clean architecture).

Intérêt
--------
- Le scénario ``prospection_outbound`` dépend d’**abstractions** stables : on peut brancher un
  ``IntentMatcherProtocol`` mock en test, ou une autre implémentation (fuzzy match, LLM) sans
  réécrire la boucle modem.
- ``typing.Protocol`` + ``@runtime_checkable`` : **structural subtyping** — ``IntentChain``
  n’a pas besoin d’hériter explicitement ; il suffit qu’il expose ``match(...)``.

Variables
---------
Aucune variable globale ; seulement des **Protocols** (contrats de méthodes).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol, runtime_checkable

from .chain import IntentMatchResult


@runtime_checkable
class IntentMatcherProtocol(Protocol):
    """
    Port « matcher d’intentions » : transcription → fichier WAV ou rien.

    ``IntentChain`` du même paquet satisfait ce contrat (méthode ``match``).
    """

    def match(self, transcript: str, pack_dir: Path, rng: random.Random) -> IntentMatchResult | None:
        ...
