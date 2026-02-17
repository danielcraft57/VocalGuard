"""
Routes API pour l'OSINT des numéros de téléphone
"""

import traceback
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from loguru import logger

from sqlalchemy.orm import Session

from backend.api.dependencies import get_config
from backend.core.config import Config
from backend.services.osint_service import OSINTService
from backend.api.models import OsintReputationResponse, PhoneNumberProfileResponse
from backend.database.database import get_db
from backend.database.models import PhoneNumberProfile


router = APIRouter()


@router.get("/osint/phone/{phone_number}", response_model=Dict[str, Any])
async def enrich_phone_number(
    phone_number: str,
    caller_name: str = Query(None, description="Nom de l'appelant (optionnel)"),
    config: Config = Depends(get_config)
):
    """
    Enrichit les informations sur un numéro de téléphone via OSINT
    
    Args:
        phone_number: Numéro de téléphone à analyser
        caller_name: Nom de l'appelant (optionnel, pour détection commerciale)
        config: Configuration de l'application
        
    Returns:
        Informations enrichies sur le numéro
    """
    try:
        logger.info(f"Requête OSINT pour le numéro: {phone_number}, nom: {caller_name}")
        osint_service = OSINTService(config)
        result = await osint_service.enrich_phone_number(phone_number, caller_name)
        logger.info(f"Résultat OSINT obtenu avec succès pour {phone_number}")
        return result
    except Exception as e:
        error_detail = str(e)
        traceback_str = traceback.format_exc()
        logger.error(f"Erreur OSINT pour {phone_number}: {error_detail}\n{traceback_str}")
        # Retourner un message d'erreur plus détaillé en mode debug
        if config.api_debug:
            raise HTTPException(status_code=500, detail=f"Erreur OSINT: {error_detail}\n{traceback_str}")
        else:
            raise HTTPException(status_code=500, detail=f"Erreur OSINT: {error_detail}")


@router.get("/osint/reputation/{phone_number}", response_model=OsintReputationResponse)
async def check_reputation(
    phone_number: str,
    caller_name: str = Query(None, description="Nom de l'appelant (optionnel)"),
    config: Config = Depends(get_config)
):
    """
    Vérifie la réputation d'un numéro de téléphone
    
    Args:
        phone_number: Numéro de téléphone à vérifier
        caller_name: Nom de l'appelant (optionnel, pour détection commerciale)
        config: Configuration de l'application
        
    Returns:
        Informations sur la reputation
    """
    try:
        osint_service = OSINTService(config)
        raw_result = await osint_service.check_reputation(phone_number, caller_name)
        return OsintReputationResponse(**raw_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur OSINT: {str(e)}")


@router.get("/osint/tools", response_model=Dict[str, Any])
async def get_available_tools(config: Config = Depends(get_config)):
    """
    Liste les outils OSINT disponibles
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Liste des outils disponibles
    """
    osint_service = OSINTService(config)
    return {
        "is_wsl": osint_service.is_wsl,
        "available_tools": osint_service.available_tools,
        "tools_path": str(osint_service.osint_tools_path),
    }


@router.post("/osint/install/phoneinfoga")
async def install_phoneinfoga(config: Config = Depends(get_config)):
    """
    Installe phoneinfoga (nécessite WSL/Kali Linux)
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Résultat de l'installation
    """
    osint_service = OSINTService(config)
    
    if not osint_service.is_wsl:
        raise HTTPException(
            status_code=400,
            detail="L'installation de phoneinfoga nécessite WSL ou Linux"
        )
    
    success = osint_service.install_phoneinfoga()
    
    if success:
        return {"message": "phoneinfoga installé avec succès"}
    else:
        raise HTTPException(
            status_code=500,
            detail="Échec de l'installation de phoneinfoga"
        )


@router.get("/osint/commercial/{phone_number}", response_model=Dict[str, Any])
async def detect_commercial(
    phone_number: str,
    caller_name: str = Query(None, description="Nom de l'appelant (optionnel)"),
    config: Config = Depends(get_config)
):
    """
    Détecte si un numéro est commercial ou télémarketeur
    
    Args:
        phone_number: Numéro de téléphone à analyser
        caller_name: Nom de l'appelant (optionnel)
        config: Configuration de l'application
        
    Returns:
        Informations sur la détection commerciale
    """
    try:
        osint_service = OSINTService(config)
        result = osint_service.commercial_detector.detect_commercial(phone_number, caller_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur détection commerciale: {str(e)}")


@router.get("/osint/patterns", response_model=Dict[str, Any])
async def get_patterns(config: Config = Depends(get_config)):
    """
    Retourne tous les patterns de détection commerciale configurés
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Patterns de détection
    """
    try:
        osint_service = OSINTService(config)
        patterns = osint_service.commercial_detector.get_patterns()
        return patterns
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@router.get(
    "/osint/profile/{phone_number}",
    response_model=PhoneNumberProfileResponse,
)
async def get_osint_profile(
    phone_number: str,
    db: Session = Depends(get_db),
):
    """
    Retourne le profil OSINT persiste pour un numero donne.
    
    Args:
        phone_number: Numero pour lequel chercher un profil.
        db: Session de base de donnees.
    
    Returns:
        Profil `PhoneNumberProfileResponse` ou erreur 404.
    """
    profile = (
        db.query(PhoneNumberProfile)
        .filter(PhoneNumberProfile.phone_number == phone_number)
        .order_by(PhoneNumberProfile.last_checked_at.desc().nullslast())
        .first()
    )

    if profile is None:
        raise HTTPException(status_code=404, detail="Profil OSINT introuvable pour ce numero")

    return PhoneNumberProfileResponse.from_orm(profile)

