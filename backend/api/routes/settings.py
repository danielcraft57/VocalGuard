"""
Routes API pour exposer la configuration metier au frontend.
"""

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_config
from backend.core.config import Config
from backend.api.models import SettingsResponse


router = APIRouter()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(config: Config = Depends(get_config)) -> SettingsResponse:
    """
    Retourne un snapshot de la configuration utile au frontend.
    """
    return SettingsResponse(
        database_url=config.database_url,
        api_host=config.api_host,
        api_port=config.api_port,
        modem_port=config.modem_port,
        voice_language=config.voice_language,
        rings_before_answer=config.rings_before_answer,
        voicemail_enabled=config.voicemail_enabled,
    )

