"""
Routes API pour les messages vocaux
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import List, Optional

from backend.api.dependencies import get_config, get_voicemail_repository
from backend.core.config import Config
from backend.repositories.voicemail_repository import VoicemailRepository
from backend.api.models import VoicemailResponse


router = APIRouter()


def _resolve_voicemail_audio(config: Config, audio_file: str) -> Optional[Path]:
    """
    Resout le chemin du WAV message (relatif a base_path ou absolu).

    @param config Config applicative.
    @param audio_file Chemin stocke en base (ex. messages/vm_1_....wav).
    @returns Path existant ou None.
    """
    if not audio_file or ".." in audio_file:
        return None
    raw = Path(audio_file)
    if raw.is_absolute() and raw.exists():
        return raw
    norm = audio_file.replace("\\", "/").strip().lstrip("/")
    if not (norm.startswith("messages/") or norm.startswith("recordings/")):
        return None
    base = Path(config.base_path) if config.base_path else Path.cwd()
    candidate = (base / norm).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate if candidate.exists() else None


@router.get("/voicemails", response_model=List[VoicemailResponse])
async def get_voicemails(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_read: Optional[bool] = None,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """
    Recupere la liste des messages vocaux.

    @param skip Nombre d enregistrements a sauter
    @param limit Nombre maximum d enregistrements
    @param is_read Filtrer par statut de lecture
    @param voicemail_repo Repository des messages vocaux
    @returns Liste des messages vocaux
    """
    if is_read is False:
        return [
            VoicemailResponse.model_validate(vm)
            for vm in voicemail_repo.get_unread(skip=skip, limit=limit)
        ]
    voicemails = voicemail_repo.get_recent(limit=skip + limit)
    if is_read is True:
        voicemails = [vm for vm in voicemails if vm.is_read]
    return [VoicemailResponse.model_validate(vm) for vm in voicemails[skip : skip + limit]]


@router.get("/voicemails/{voicemail_id}", response_model=VoicemailResponse)
async def get_voicemail(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """Recupere un message vocal specifique."""
    voicemail = voicemail_repo.get_by_id(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouve")
    return VoicemailResponse.model_validate(voicemail)


@router.put("/voicemails/{voicemail_id}/read")
async def mark_voicemail_read(
    voicemail_id: int,
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """Marque un message vocal comme lu."""
    voicemail = voicemail_repo.mark_as_read(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouve")
    return {"message": "Message vocal marque comme lu"}


@router.get("/voicemails/{voicemail_id}/audio")
async def get_voicemail_audio(
    voicemail_id: int,
    config: Config = Depends(get_config),
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """Sert le fichier WAV d un message vocal."""
    voicemail = voicemail_repo.get_by_id(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouve")
    if not voicemail.audio_file:
        raise HTTPException(status_code=404, detail="Fichier audio non disponible")
    audio_path = _resolve_voicemail_audio(config, voicemail.audio_file)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Fichier audio introuvable")
    return FileResponse(
        str(audio_path),
        media_type="audio/wav",
        filename=f"voicemail_{voicemail_id}.wav"
    )


@router.delete("/voicemails/{voicemail_id}")
async def delete_voicemail(
    voicemail_id: int,
    config: Config = Depends(get_config),
    voicemail_repo: VoicemailRepository = Depends(get_voicemail_repository)
):
    """Supprime un message vocal et son fichier audio si present."""
    voicemail = voicemail_repo.get_by_id(voicemail_id)
    if not voicemail:
        raise HTTPException(status_code=404, detail="Message vocal non trouve")
    audio_path = _resolve_voicemail_audio(config, voicemail.audio_file or "")
    if not voicemail_repo.delete(voicemail_id):
        raise HTTPException(status_code=404, detail="Message vocal non trouve")
    if audio_path and audio_path.exists():
        try:
            audio_path.unlink()
        except OSError:
            pass
    return {"message": "Message vocal supprime"}
