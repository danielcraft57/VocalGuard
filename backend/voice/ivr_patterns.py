"""
Moteur d'IVR base sur des patterns/questions-reponses.

Ce module factorise la logique utilisee par le script `test_patterns_voice`
pour qu'elle soit reutilisable par le backend (CallManager, API, etc.).
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.core.config import Config
from backend.voice.intents_loader import load_intents_ivr, find_intent


class IvrPatternsEngine:
    """
    Moteur simple d'IVR base sur un fichier YAML de strategies (intents_ivr.yaml).

    - charge les intents au demarrage
    - fait le matching texte -> intent
    - expose la reponse texte et le nom de fichier WAV conseille (ivr_xxx.wav)
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.base_path = Path(config.base_path) if getattr(config, "base_path", None) else Path(".")
        self._intents: List[Dict[str, Any]] = []
        self._default_intent: Dict[str, Any] = {}
        self._exit_intent: Dict[str, Any] = {}
        self._load_intents()

    def _load_intents(self) -> None:
        """Charge les intents IVR depuis config/intents_ivr.yaml ou le fichier exemple."""
        intents, default_intent, exit_intent = load_intents_ivr(base_path=self.base_path)
        self._intents = intents
        self._default_intent = default_intent
        self._exit_intent = exit_intent
        logger.info(
            "Moteur IVR patterns initialise: {} intents, intent par defaut='{}', exit='{}'",
            len(self._intents),
            self._default_intent.get("name"),
            self._exit_intent.get("name"),
        )

    def reload(self) -> None:
        """Recharge le fichier d'intents (utile si intents_ivr.yaml est modifie a chaud)."""
        self._load_intents()

    def match_intent(self, user_text: str) -> Dict[str, Any]:
        """
        Retourne l'intent choisi pour un texte utilisateur.

        Returns:
            dict contenant au moins: name, response, filename.
        """
        intent = find_intent(user_text, self._intents, self._default_intent, self._exit_intent)
        logger.debug(
            "Intent IVR choisi pour '{}': {} -> fichier {}",
            user_text,
            intent.get("name"),
            intent.get("filename"),
        )
        return intent

    def is_exit_intent(self, intent: Dict[str, Any]) -> bool:
        """True si l'intent correspond a l'intent de sortie."""
        if not intent:
            return False
        return intent.get("name") == self._exit_intent.get("name")

    def get_response_and_filename(self, intent: Dict[str, Any]) -> Tuple[str, str]:
        """
        Extrait (response, filename) d'un intent avec des valeurs par defaut raisonnables.
        """
        response = intent.get("response") or self._default_intent.get("response") or ""
        filename = intent.get("filename") or self._default_intent.get("filename") or "ivr_unknown.wav"
        return response, filename

