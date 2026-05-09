"""
**Strategy** : politique d’exécution d’un dialogue prospection (paramètres + règles + observateurs).

Intérêt
--------
- Regroupe en un seul objet tout ce qui **varie** entre campagnes (durées, plafonds, specs)
  sans multiplier les paramètres dans ``prospection_outbound.run``.
- Nouvelle campagne = nouvelle ``ProspectionDialoguePolicy`` (ou sous-classe / factory) sans
  toucher au câblage modem/Vosk.
- ``effective_listen_seconds`` : **tronque** l’écoute STT pour respecter le budget wall-clock
  restant (évite un ``pump`` plus long que le temps disponible).

Variables (``ProspectionDialoguePolicy``)
-----------------------------------------
- ``config`` : ``ProspectionDialogueConfig`` (chemins JSON, tags terminaux, etc.).
- ``listen_sec_per_turn`` : durée **demandée** par tour STT (tronquée si deadline).
- ``wall_budget_sec`` : budget global optionnel ; ``None`` = pas de limite wall-clock.
- ``continue_dialogue`` : ``DialogueSpecification`` composite (ET logique).
- ``event_bus`` : ``DialogueEventBus`` pour les observateurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

from .config import ProspectionDialogueConfig
from .deadline import CallDeadline
from .events import DialogueEventBus, loguru_dialogue_sink
from .specification import (
    DialogueSpecification,
    default_continue_dialogue_spec,
)


@dataclass(frozen=True)
class ProspectionDialoguePolicy:
    """
    Stratégie complète : **quoi** matcher, **combien de temps** écouter, **quand s’arrêter**.

    Immuable après construction : le snapshot (memento) porte l’état dynamique à part.
    """

    config: ProspectionDialogueConfig
    listen_sec_per_turn: float
    wall_budget_sec: float | None
    continue_dialogue: DialogueSpecification
    event_bus: DialogueEventBus

    def effective_listen_seconds(self, deadline: CallDeadline | None) -> float:
        """
        Durée réelle passée à ``pump_vrx_pcm16_to_vosk`` pour ce tour.

        Si ``deadline`` est actif, on ne dépasse pas ``deadline.remaining_sec()`` (minimum 0,5 s
        tant qu’il reste du budget, sinon 0,05 s pour terminer proprement).
        """
        base = max(1.0, float(self.listen_sec_per_turn))
        if deadline is None:
            return base
        rem = deadline.remaining_sec()
        if rem <= 0.05:
            return 0.05
        return max(0.5, min(base, rem))


def build_dialogue_policy(
    *,
    intent_json_paths: tuple[Path, ...],
    pack_dir: Path,
    max_reply_turns: int,
    terminal_tags: FrozenSet[str],
    rng_seed: int | None,
    listen_sec_per_turn: float,
    wall_budget_sec: float | None = None,
    event_bus: DialogueEventBus | None = None,
    continue_rule: DialogueSpecification | None = None,
    attach_default_log_sink: bool = True,
) -> ProspectionDialoguePolicy:
    """
    Fabrique une policy prête pour le scénario modem.

    :param event_bus: si ``None``, crée un bus neuf ; si ``attach_default_log_sink``, y branche
        ``loguru_dialogue_sink`` **une seule fois** (évite les doublons si vous passez un bus déjà configuré).
    """
    cfg = ProspectionDialogueConfig(
        intent_json_paths=intent_json_paths,
        pack_dir=pack_dir,
        max_reply_turns=max(1, int(max_reply_turns)),
        terminal_intent_tags=terminal_tags,
        rng_seed=rng_seed,
    )
    bus = event_bus or DialogueEventBus()
    if attach_default_log_sink and event_bus is None:
        bus.subscribe(loguru_dialogue_sink)
    rule = continue_rule or default_continue_dialogue_spec()
    return ProspectionDialoguePolicy(
        config=cfg,
        listen_sec_per_turn=float(listen_sec_per_turn),
        wall_budget_sec=float(wall_budget_sec) if wall_budget_sec is not None else None,
        continue_dialogue=rule,
        event_bus=bus,
    )
