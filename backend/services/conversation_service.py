"""
Service de conversation pour les appels VocalGuard.

Ce service centralise la logique de generation de reponses
en fonction d'une transcription, en s'appuyant sur
des patterns metier et un fallback deterministic.
"""

from pathlib import Path
from typing import Optional

from backend.core.response_patterns import ResponsePatternManager


class ConversationService:
    """
    Service responsable de transformer une transcription texte
    en reponse textuelle destinee a etre lue a l'appelant.
    """

    def __init__(self) -> None:
        """
        Initialise le service de conversation.
        """
        self._pattern_manager = ResponsePatternManager()
        try:
            from backend.ml.ml_intents import CommercialMlConversationBrain

            project_root = Path(__file__).resolve().parents[2]

            cwd = Path.cwd()
            if (cwd / "backend").exists() or (cwd / "config").exists():
                resolved_root = cwd
            else:
                resolved_root = project_root

            self._ml_brain = CommercialMlConversationBrain(resolved_root)
        except Exception:
            self._ml_brain = None

    async def generate_reply(self, transcription: str) -> Optional[str]:
        """
        Genere une reponse a partir de la transcription.
        
        Cette version utilise des patterns et garde un fallback simple
        pour les transcriptions ambiguës.
        
        Args:
            transcription: Texte reconnu lors de l'appel.
        
        Returns:
            Reponse a lire ou None si aucune reponse.
        """
        if not transcription:
            return None

        # 0) Couche facultative apprentissage supervise sur intents DanielCraft (`data/` + `models/`).
        if self._ml_brain:
            ml_reply = self._ml_brain.generate_reply_if_confident(transcription)
            if ml_reply:
                return ml_reply

        try:
            response = self._pattern_manager.generate_response(transcription)
            if response:
                return response
        except Exception:
            return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

        return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

