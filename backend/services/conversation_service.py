"""
Service de conversation pour les appels VocalGuard.

Ce service centralise la logique de generation de reponses
en fonction d'une transcription, en s'appuyant eventuellement
sur un modele de langue externe (Ollama, LLM, etc.).
"""

from typing import Optional

from loguru import logger

from backend.ai.ollama_client import OllamaClient


class ConversationService:
    """
    Service responsable de transformer une transcription texte
    en reponse textuelle destinee a etre lue a l'appelant.
    """

    def __init__(self, ollama_client: Optional[OllamaClient] = None) -> None:
        """
        Initialise le service de conversation.
        
        Args:
            ollama_client: Client Ollama optionnel pour les reponses naturelles.
        """
        self._ollama_client = ollama_client

    async def generate_reply(self, transcription: str) -> Optional[str]:
        """
        Genere une reponse a partir de la transcription.
        
        Cette premiere version se contente d'appeler Ollama si disponible,
        avec un fallback simple.
        
        Args:
            transcription: Texte reconnu lors de l'appel.
        
        Returns:
            Reponse a lire ou None si aucune reponse.
        """
        if not transcription:
            return None

        if not self._ollama_client:
            # Fallback simple pour les premiers essais.
            return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

        try:
            response = self._ollama_client.generate(transcription, use_history=True)
            if response:
                return response
        except Exception as exc:
            logger.warning(f"Erreur lors de la generation de reponse avec Ollama: {exc}")

        return "Je n'ai pas bien compris. Voulez-vous laisser un message?"

