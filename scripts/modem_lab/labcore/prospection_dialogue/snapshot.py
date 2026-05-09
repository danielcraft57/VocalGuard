"""
**Memento** léger de l’avancement d’un appel de prospection.

Permet de journaliser ou de reprendre plus tard : numéro de tour, tags déjà joués,
transcription du dernier segment, drapeau d’arrêt anticipé.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ConversationSnapshot:
    """
    État conversationnel **mutable** (mis à jour après chaque tour STT / lecture).

    Attributes
    ----------
    reply_turns_completed:
        Nombre de tours « écoute → réponse » **terminés** (incrémenté après lecture d’un WAV intent).
    played_intent_tags:
        Liste ordonnée des tags d’intent dont on a déjà joué un WAV (traçabilité).
    last_turn_transcript:
        Texte Vosk concaténé du **dernier** segment écouté (diagnostic).
    stop_dialogue:
        Si vrai : la boucle dialogue ne doit plus continuer (intent terminal ou limite atteinte).
    """

    reply_turns_completed: int = 0
    played_intent_tags: list[str] = field(default_factory=list)
    last_turn_transcript: str = ""
    stop_dialogue: bool = False

    def record_reply_played(self, intent_tag: str, *, terminal: bool) -> None:
        """Après lecture réussie d’un WAV de réponse."""
        self.reply_turns_completed += 1
        self.played_intent_tags.append(intent_tag)
        if terminal:
            self.stop_dialogue = True

    def to_jsonable(self) -> dict[str, Any]:
        """Sérialisation JSON-friendly (rapport de session, logs)."""
        return asdict(self)
