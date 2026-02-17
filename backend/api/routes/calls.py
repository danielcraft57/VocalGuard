"""
Routes API pour les appels
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from backend.api.dependencies import get_call_repository, get_call_service
from backend.repositories.call_repository import CallRepository
from backend.services.call_service import CallService
from backend.api.models import CallResponse, CallListResponse


router = APIRouter()


@router.get("/calls", response_model=CallListResponse)
async def get_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    call_repo: CallRepository = Depends(get_call_repository)
):
    """
    Récupère la liste des appels
    
    Args:
        skip: Nombre d'enregistrements à sauter
        limit: Nombre maximum d'enregistrements à retourner
        status: Filtrer par statut
        phone_number: Filtrer par numéro de téléphone
        call_repo: Repository des appels
        
    Returns:
        Liste des appels
    """
    filters = {}
    if status:
        filters["status"] = status
    if phone_number:
        filters["phone_number"] = phone_number
    
    total = call_repo.count(**filters)
    calls = call_repo.get_all(skip=skip, limit=limit, **filters)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "calls": [CallResponse.model_validate(call) for call in calls]
    }


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    call_repo: CallRepository = Depends(get_call_repository)
):
    """
    Récupère un appel spécifique
    
    Args:
        call_id: ID de l'appel
        call_repo: Repository des appels
        
    Returns:
        Détails de l'appel
    """
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel non trouvé")
    
    return CallResponse.model_validate(call)


@router.delete("/calls/{call_id}")
async def delete_call(
    call_id: int,
    call_repo: CallRepository = Depends(get_call_repository)
):
    """
    Supprime un appel
    
    Args:
        call_id: ID de l'appel
        call_repo: Repository des appels
    """
    if not call_repo.delete(call_id):
        raise HTTPException(status_code=404, detail="Appel non trouvé")
    
    return {"message": "Appel supprimé"}

