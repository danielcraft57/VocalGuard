"""
**Observer** léger : bus d’événements dialogue (découplage scénario / métriques / logs).

Intérêt
--------
- ``prospection_outbound`` émet des faits (« tour démarré », « intent matché ») sans connaître
  les abonnés (logs structurés, future export OpenTelemetry, tests qui assert sur une liste).
- Chaque handler est isolé : une exception dans un abonné **n’interrompt pas** les autres.

Variables
---------
- ``DialogueEvent.kind`` : chaîne stable (voir ``DialogueEventKind``).
- ``DialogueEvent.payload`` : dict sérialisable (numéro de tour, tag, chemins, etc.).
- ``DialogueEventBus._handlers`` : liste de callbacks ``(DialogueEvent) -> None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger


@dataclass(frozen=True)
class DialogueEvent:
    """Message immuable passé aux observateurs."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


class DialogueEventKind:
    """Constantes de ``kind`` pour éviter les fautes de frappe."""

    DIALOGUE_STARTED = "dialogue_started"
    TURN_STT_START = "turn_stt_start"
    TURN_STT_DONE = "turn_stt_done"
    INTENT_MATCHED = "intent_matched"
    INTENT_NO_MATCH = "intent_no_match"
    WAV_REPLY_START = "wav_reply_start"
    DIALOGUE_STOPPED = "dialogue_stopped"
    DIALOGUE_ERROR = "dialogue_error"


DialogueHandler = Callable[[DialogueEvent], None]


class DialogueEventBus:
    """
    Registre **publish / subscribe** synchrone (même thread asyncio que le scénario).

    Pas de file async : les handlers doivent rester rapides (log, append liste).
    """

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: list[DialogueHandler] = []

    def subscribe(self, handler: DialogueHandler) -> None:
        """Enregistre un observateur (appelé dans l’ordre d’inscription)."""
        self._handlers.append(handler)

    def emit(self, kind: str, **payload: Any) -> None:
        """Diffuse un événement à tous les abonnés."""
        ev = DialogueEvent(kind=kind, payload=dict(payload))
        for fn in list(self._handlers):
            try:
                fn(ev)
            except Exception as e:
                logger.warning("DialogueEventBus handler échoué (kind={}): {}", kind, e)


def loguru_dialogue_sink(ev: DialogueEvent) -> None:
    """
    Observateur par défaut : une ligne loguru par événement (niveau INFO).

    Utile en prod / lab sans code supplémentaire ; remplaçable par ``subscribe`` custom.
    """
    logger.info("dialogue_event kind={} payload={}", ev.kind, ev.payload)
