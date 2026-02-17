"""
Routes API pour la configuration
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import Config


router = APIRouter()


class ConfigResponse(BaseModel):
    """Modèle de réponse pour la configuration"""
    api_host: str
    api_port: int
    voice_recognition_engine: str
    voice_synthesis_engine: str
    voice_language: str
    block_enabled: bool
    voicemail_enabled: bool


# Note: La configuration devrait être injectée via une dépendance FastAPI
# Pour l'instant, on utilise une variable globale ou on la passe différemment

@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """
    Récupère la configuration actuelle
    
    Returns:
        Configuration actuelle
    """
    # TODO: Injecter la config via une dépendance FastAPI
    # Pour l'instant, créer une instance temporaire
    from backend.core.config import Config
    config = Config()
    
    return ConfigResponse(
        api_host=config.api_host,
        api_port=config.api_port,
        voice_recognition_engine=config.voice_recognition_engine,
        voice_synthesis_engine=config.voice_synthesis_engine,
        voice_language=config.voice_language,
        block_enabled=config.block_enabled,
        voicemail_enabled=config.voicemail_enabled
    )

