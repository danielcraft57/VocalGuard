"""
**Specification** : règles composables « est-ce qu’on peut enchaîner un tour de plus ? ».

Intérêt
--------
- Sépare la **logique métier** (« pas après stop RGPD », « pas au-delà de N tours »,
  « plus de temps wall-clock ») du code de boucle dans ``prospection_outbound``.
- Les règles se **combinent** (ET logique) sans empiler des ``if`` illisibles.
- Facile à **tester unitairement** : un snapshot + un contexte → booléen.

Types principaux
----------------
- ``DialogueContext`` : données **du tour envisagé** (index, plafond, deadline optionnelle).
- ``DialogueSpecification`` : protocole ``is_satisfied_by(snapshot, ctx)``.
- ``AllOf`` : combinateur (toutes les specs doivent passer).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .deadline import CallDeadline
from .snapshot import ConversationSnapshot


@dataclass(frozen=True)
class DialogueContext:
    """
    Contexte **immuable** pour évaluer une spec à l’entrée du tour ``next_turn_index``.

    Attributes
    ----------
    next_turn_index:
        Numéro du tour **1-based** que l’on s’apprête à exécuter (écoute STT puis match).
    max_turns:
        Plafond configuré (``ProspectionDialogueConfig.max_reply_turns``).
    deadline:
        Si non ``None``, le temps wall-clock restant doit suffire pour continuer.
    """

    next_turn_index: int
    max_turns: int
    deadline: CallDeadline | None


@runtime_checkable
class DialogueSpecification(Protocol):
    """Contrat : une règle sur le couple (memento, contexte)."""

    def is_satisfied_by(self, snapshot: ConversationSnapshot, ctx: DialogueContext) -> bool:
        ...


class NotStoppedSpecification:
    """Refus si le memento signale déjà un arrêt (intent terminal traité)."""

    def is_satisfied_by(self, snapshot: ConversationSnapshot, ctx: DialogueContext) -> bool:
        _ = ctx
        return not snapshot.stop_dialogue


class WithinMaxTurnsSpecification:
    """Refus si le prochain tour dépasse ``max_turns``."""

    def is_satisfied_by(self, snapshot: ConversationSnapshot, ctx: DialogueContext) -> bool:
        _ = snapshot
        return ctx.next_turn_index <= ctx.max_turns


class BeforeDeadlineSpecification:
    """Refus si ``deadline`` existe et est expirée (plus de budget wall-clock)."""

    def is_satisfied_by(self, snapshot: ConversationSnapshot, ctx: DialogueContext) -> bool:
        _ = snapshot
        if ctx.deadline is None:
            return True
        return not ctx.deadline.expired()


class AllOfSpecifications:
    """
    Pattern **Composite** sur des Specification : toutes doivent être vraies (ET logique).

    ``parts`` : tuple de specs évaluées **dans l’ordre** ; court-circuit au premier False.
    """

    __slots__ = ("_parts",)

    def __init__(self, *parts: DialogueSpecification) -> None:
        self._parts: tuple[DialogueSpecification, ...] = tuple(parts)

    def is_satisfied_by(self, snapshot: ConversationSnapshot, ctx: DialogueContext) -> bool:
        for p in self._parts:
            if not p.is_satisfied_by(snapshot, ctx):
                return False
        return True


def default_continue_dialogue_spec() -> AllOfSpecifications:
    """
    Politique par défaut : pas d’arrêt memento, encore des tours, deadline non dépassée.

    Utilisée par ``ProspectionDialoguePolicy`` sauf injection explicite (tests / campagne).
    """
    return AllOfSpecifications(
        NotStoppedSpecification(),
        WithinMaxTurnsSpecification(),
        BeforeDeadlineSpecification(),
    )
