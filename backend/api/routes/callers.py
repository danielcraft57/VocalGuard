"""
Routes API pour les appelants
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from backend.api.dependencies import get_caller_repository, get_block_service
from backend.repositories.caller_repository import CallerRepository
from backend.services.block_service import BlockService
from backend.api.models import CallerResponse, CallerCreate, CallerUpdate, WhitelistAddRequest, BlockAddRequest


router = APIRouter()


@router.get("/callers", response_model=List[CallerResponse])
async def get_callers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_blocked: Optional[bool] = None,
    is_whitelisted: Optional[bool] = None,
    caller_repo: CallerRepository = Depends(get_caller_repository)
):
    """
    Récupère la liste des appelants
    
    Args:
        skip: Nombre d'enregistrements à sauter
        limit: Nombre maximum d'enregistrements à retourner
        is_blocked: Filtrer par statut de blocage
        is_whitelisted: Filtrer par statut de liste blanche
        caller_repo: Repository des appelants
        
    Returns:
        Liste des appelants
    """
    filters = {}
    if is_blocked is not None:
        filters["is_blocked"] = is_blocked
    if is_whitelisted is not None:
        filters["is_whitelisted"] = is_whitelisted
    
    callers = caller_repo.get_all(skip=skip, limit=limit, **filters)
    return [CallerResponse.model_validate(caller) for caller in callers]


@router.get("/callers/{caller_id}", response_model=CallerResponse)
async def get_caller(
    caller_id: int,
    caller_repo: CallerRepository = Depends(get_caller_repository)
):
    """
    Récupère un appelant spécifique
    
    Args:
        caller_id: ID de l'appelant
        caller_repo: Repository des appelants
        
    Returns:
        Détails de l'appelant
    """
    caller = caller_repo.get_by_id(caller_id)
    if not caller:
        raise HTTPException(status_code=404, detail="Appelant non trouvé")
    
    return CallerResponse.model_validate(caller)


@router.post("/callers", response_model=CallerResponse)
async def create_caller(
    caller_data: CallerCreate,
    caller_repo: CallerRepository = Depends(get_caller_repository)
):
    """
    Crée un nouvel appelant
    
    Args:
        caller_data: Données de l'appelant
        caller_repo: Repository des appelants
        
    Returns:
        Appelant créé
    """
    # Vérifier si l'appelant existe déjà
    existing = caller_repo.get_by_phone_number(caller_data.phone_number)
    if existing:
        raise HTTPException(status_code=400, detail="Cet appelant existe déjà")
    
    caller = caller_repo.create(**caller_data.dict())
    return CallerResponse.model_validate(caller)


@router.put("/callers/{caller_id}", response_model=CallerResponse)
async def update_caller(
    caller_id: int,
    caller_data: CallerUpdate,
    caller_repo: CallerRepository = Depends(get_caller_repository)
):
    """
    Met à jour un appelant
    
    Args:
        caller_id: ID de l'appelant
        caller_data: Données à mettre à jour
        caller_repo: Repository des appelants
        
    Returns:
        Appelant mis à jour
    """
    caller = caller_repo.update(caller_id, **caller_data.dict(exclude_unset=True))
    if not caller:
        raise HTTPException(status_code=404, detail="Appelant non trouvé")
    
    return CallerResponse.model_validate(caller)


@router.delete("/callers/{caller_id}")
async def delete_caller(
    caller_id: int,
    caller_repo: CallerRepository = Depends(get_caller_repository)
):
    """
    Supprime un appelant
    
    Args:
        caller_id: ID de l'appelant
        caller_repo: Repository des appelants
    """
    if not caller_repo.delete(caller_id):
        raise HTTPException(status_code=404, detail="Appelant non trouvé")
    
    return {"message": "Appelant supprimé"}


@router.post("/callers/whitelist", response_model=CallerResponse)
async def add_to_whitelist(
    payload: WhitelistAddRequest,
    block_service: BlockService = Depends(get_block_service),
    caller_repo: CallerRepository = Depends(get_caller_repository),
):
    """
    Ajoute un numéro à la liste blanche (inspiré callattendant Permitted).
    Crée ou met à jour l'appelant avec is_whitelisted=True, is_blocked=False.
    """
    await block_service.whitelist_caller(payload.phone_number)
    caller = caller_repo.get_by_phone_number(payload.phone_number)
    if caller and (payload.name is not None or payload.notes is not None):
        caller_repo.update(
            caller.id,
            name=payload.name if payload.name is not None else caller.name,
            notes=payload.notes if payload.notes is not None else caller.notes,
        )
        caller = caller_repo.get_by_id(caller.id)
    if not caller:
        raise HTTPException(status_code=500, detail="Erreur lors de l'ajout à la liste blanche")
    return CallerResponse.model_validate(caller)


@router.post("/callers/block", response_model=CallerResponse)
async def add_to_blocklist(
    payload: BlockAddRequest,
    block_service: BlockService = Depends(get_block_service),
    caller_repo: CallerRepository = Depends(get_caller_repository),
):
    """
    Ajoute un numéro à la liste noire (inspiré callattendant Blocked).
    Crée ou met à jour l'appelant avec is_blocked=True, is_whitelisted=False.
    """
    await block_service.block_caller(payload.phone_number, reason=payload.notes)
    caller = caller_repo.get_by_phone_number(payload.phone_number)
    if caller and (payload.name is not None or payload.notes is not None):
        caller_repo.update(
            caller.id,
            name=payload.name if payload.name is not None else caller.name,
            notes=payload.notes if payload.notes is not None else caller.notes,
        )
        caller = caller_repo.get_by_id(caller.id)
    if not caller:
        raise HTTPException(status_code=500, detail="Erreur lors de l'ajout à la liste noire")
    return CallerResponse.model_validate(caller)

