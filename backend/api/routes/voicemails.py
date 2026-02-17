"""
Routes API pour les messages vocaux
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional

from backend.api.dependencies import get_voicemail_repository
from backend.repositories.voicemail_repository import VoicemailRepository
from backend.api.models import VoicemailResponse


router = APIRouter()


@router.get("/voicemails", response_model=List[VoicemailResponse])
async def get_voicemails(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_read: Optional[bool] = None,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Récupère la liste des messages vocaux
    
    Args:
        skip: Nombre d'enregistrements à sauter
        limit: Nombre maximum d'enregistrements à retourner
        is_read: Filtrer par statut de lecture
        voicemail_repo: Repository des messages vocaux
        
    Returns:
        Liste des messages vocaux
    """
    filters = {}
    if is_read is not None:
        filters["is_read"] = is_read
    
    voicemails = voicemail_repo.get_all(skip=skip, limit=limit, **filters)
    return [VoicemailResponse.model_validate(vm) for vm in voicemails]


@router.get("/voicemails/{voicemail_id}", response_model=VoicemailResponse)
async def get_voicemail(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Récupère un message vocal spécifique
    
    Args:
        voicemail_id: ID du message vocal
        voicemail_repo: Repository des messages vocaux
        
    Returns:
        Détails du message vocal
    """
    voicemail = voicemail_repo.get_by_id(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouvé")
    
    return VoicemailResponse.model_validate(voicemail)


@router.put("/voicemails/{voicemail_id}/read")
async def mark_voicemail_read(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Marque un message vocal comme lu
    
    Args:
        voicemail_id: ID du message vocal
        voicemail_repo: Repository des messages vocaux
    """
    voicemail = voicemail_repo.mark_as_read(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouvé")
    
    return {"message": "Message vocal marqué comme lu"}


@router.get("/voicemails/{voicemail_id}/audio")
async def get_voicemail_audio(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Récupère le fichier audio d'un message vocal
    
    Args:
        voicemail_id: ID du message vocal
        voicemail_repo: Repository des messages vocaux
        
    Returns:
        Fichier audio
    """
    voicemail = voicemail_repo.get_by_id(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouvé")
    
    if not voicemail.audio_file:
        raise HTTPException(status_code=404, detail="Fichier audio non disponible")
    
    audio_path = Path(voicemail.audio_file)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Fichier audio introuvable")
    
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=f"voicemail_{voicemail_id}.wav"
    )


@router.delete("/voicemails/{voicemail_id}")
async def delete_voicemail(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Supprime un message vocal
    
    Args:
        voicemail_id: ID du message vocal
        voicemail_repo: Repository des messages vocaux
    """
    if not voicemail_repo.delete(voicemail_id):
        raise HTTPException(status_code=404, detail="Message vocal non trouvé")
    
    return {"message": "Message vocal supprimé"}

