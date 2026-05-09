"""
Configuration **immuable** d’une session de prospection dialogue.

Séparée du **snapshot** (``snapshot.py``) : la config décrit les règles du jeu,
le snapshot enregistre ce qui s’est passé pendant l’appel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet


@dataclass(frozen=True)
class ProspectionDialogueConfig:
    """
    Paramètres passés une fois au démarrage du scénario (CLI ou tests).

    Attributes
    ----------
    intent_json_paths:
        Liste ordonnée des fichiers JSON ``intents`` (chaîne de responsabilité) :
        le **premier** fichier est parcouru en premier ; à l’intérieur d’un fichier,
        l’**ordre des objets** dans ``"intents"`` définit la priorité entre intentions.
    pack_dir:
        Dossier des WAV générés (``{tag}_{variant:02d}.wav``).
    max_reply_turns:
        Nombre maximum d’**itérations** « écoute STT → éventuelle réponse WAV » **après**
        le message d’ouverture. ``1`` reproduit l’ancien comportement (un seul tour).
    terminal_intent_tags:
        Tags d’intention qui **coupent** la boucle après lecture du WAV (ex. au revoir, RGPD).
    rng_seed:
        Graine optionnelle du générateur pseudo-aléatoire (reproductibilité tests / debug).
    """

    intent_json_paths: tuple[Path, ...]
    pack_dir: Path
    max_reply_turns: int = 1
    terminal_intent_tags: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"n1_exit", "n1_rgpd_stop_call"})
    )
    rng_seed: int | None = None

    def __post_init__(self) -> None:
        if self.max_reply_turns < 1:
            raise ValueError("max_reply_turns doit être >= 1")
        if not self.intent_json_paths:
            raise ValueError("intent_json_paths ne doit pas être vide pour le mode dialogue")
