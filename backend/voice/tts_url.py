"""
Resolution de l'URL du service TTS distant (node15).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.core.config import Config


def resolve_tts_service_url(config: "Config") -> Optional[str]:
    """
    Retourne l'URL du service TTS distant.

    Priorite : ``TTS_SERVICE_URL`` / ``tts_service_url``, sinon fallback
    ``STT_SERVICE_URL`` (meme daemon node15 historique).

    @param config Configuration application.
    @returns URL sans slash final, ou None si aucun service distant.
    """
    tts = (getattr(config, "tts_service_url", None) or "").strip().rstrip("/")
    if tts:
        return tts
    stt = (getattr(config, "stt_service_url", None) or "").strip().rstrip("/")
    return stt or None


def resolve_tts_token(config: "Config") -> Optional[str]:
    """
    Token HTTP pour le service TTS (meme secret que STT sur node15).

    @param config Configuration application.
    @returns Token ou None.
    """
    token = (getattr(config, "stt_internal_token", None) or "").strip()
    return token or None
