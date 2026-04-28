"""
Service de conversation pour les appels VocalGuard.

Ce service centralise la logique de generation de reponses
en fonction d'une transcription, en s'appuyant sur
des patterns metier et un fallback deterministic.
"""

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

        try:
            response = self._pattern_manager.generate_response(transcription)
            if response:
                return response
        except Exception:
            return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

        return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

