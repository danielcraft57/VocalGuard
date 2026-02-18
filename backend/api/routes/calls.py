"""
Routes API pour les appels.
Avec with_osint=1, la reputation OSINT est lue depuis la table phone_number_profiles (pas d'appel OSINT en direct).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.api.dependencies import get_call_repository, get_db
from backend.repositories.call_repository import CallRepository
from backend.api.models import CallResponse, CallListResponse, OsintReputationResponse
from backend.database.models import Call, PhoneNumberProfile


router = APIRouter()


def _profile_to_osint_response(profile: PhoneNumberProfile, phone_number: str) -> OsintReputationResponse:
    """
    Construit OsintReputationResponse a partir d'un PhoneNumberProfile (reputation + lieu + operateur).
    La reputation en base n'est remplie que par des sources externes (NumLookup, phoneinfoga).
    Si on a lieu/operateur (détection FR) mais pas de reputation, on renvoie "neutral" (non évaluée).
    """
    rep = (profile.reputation or "unknown").strip() or "unknown"
    if rep == "unknown" and (profile.region or profile.city or profile.operator):
        rep = "neutral"
    conf = profile.confidence
    if conf is not None:
        conf_float = float(conf) / 100.0
    else:
        conf_float = 0.0
    rec = "review"
    if profile.is_scam or profile.is_spam or profile.is_telemarketer:
        rec = "block"
    elif rep == "high":
        rec = "allow"
    elif rep == "neutral":
        rec = "review"
    return OsintReputationResponse(
        phone_number=phone_number,
        reputation=rep,
        is_spam=profile.is_spam or False,
        is_scam=profile.is_scam or False,
        is_commercial=profile.is_commercial or False,
        is_telemarketer=profile.is_telemarketer or False,
        confidence=conf_float,
        sources=["database"],
        recommendation=rec,
        city=profile.city or None,
        region=profile.region or None,
        operator=profile.operator or None,
    )


@router.get("/calls", response_model=CallListResponse)
async def get_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = None,
    phone_number: Optional[str] = None,
    with_osint: bool = Query(False, description="Inclure la reputation OSINT depuis la base (rapide)"),
    call_repo: CallRepository = Depends(get_call_repository),
    db: Session = Depends(get_db),
):
    """
    Recupere la liste des appels.
    Avec with_osint=true, joint les profils OSINT deja en base (pas d'appel API OSINT).
    """
    filters = {}
    if status:
        filters["status"] = status
    if phone_number:
        filters["phone_number"] = phone_number

    total = call_repo.count(**filters)
    calls = call_repo.get_all(skip=skip, limit=limit, **filters)

    if not with_osint:
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "calls": [CallResponse.model_validate(call) for call in calls],
        }

    phones = list({c.phone_number for c in calls if c.phone_number})
    profile_by_phone: dict[str, PhoneNumberProfile] = {}
    if phones:
        rows = (
            db.query(PhoneNumberProfile)
            .filter(PhoneNumberProfile.phone_number.in_(phones))
            .order_by(PhoneNumberProfile.phone_number, desc(PhoneNumberProfile.last_checked_at))
            .all()
        )
        for p in rows:
            if p.phone_number not in profile_by_phone:
                profile_by_phone[p.phone_number] = p

    result_calls = []
    for call in calls:
        data = CallResponse.model_validate(call).model_dump()
        if call.phone_number and call.phone_number in profile_by_phone:
            data["osint"] = _profile_to_osint_response(profile_by_phone[call.phone_number], call.phone_number)
        else:
            data["osint"] = None
        result_calls.append(CallResponse(**data))

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "calls": result_calls,
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

