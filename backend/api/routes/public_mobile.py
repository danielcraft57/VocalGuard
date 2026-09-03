"""Endpoints API publique dedies a l application mobile."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.api.dependencies import get_block_service, get_config, get_voicemail_repository
from backend.api.models import (
    MobileClaimRequest,
    MobileClaimResponse,
    TrustedContactImportRequest,
    VoicemailResponse,
)
from backend.api.routes.public_api import (
    _digits,
    _require_public_token,
    _require_token_permission,
)
from backend.api.routes.calls import (
    DtmfRequest,
    OutgoingCallActionResponse,
    OutgoingCallStartRequest,
)
from backend.api.routes.voicemails import _resolve_voicemail_audio
from backend.core.config import Config
from backend.database.database import get_db
from backend.database.models import ApiPublicToken, Call, Caller, MobilePairingSession, Voicemail
from backend.services.pairing_time import is_pairing_expired, utc_now_naive
from backend.repositories.caller_repository import CallerRepository
from backend.services.block_service import BlockService
from backend.voice.audio_utils import export_listen_preview_wav

router = APIRouter(prefix="/public", tags=["public-mobile"])

# Fenetre de re-sync messages vocaux (transcription STT arrive souvent apres le 1er delta).
_VM_DELTA_LOOKBACK_HOURS = 72


def _mobile_voicemail_audio_path(source: Path) -> Path:
    """
    WAV 16-bit lisible sur mobile (expo-av ne gere pas bien le 8 kHz 8-bit modem).

    @param source Fichier WAV modem stocke.
    @returns Chemin WAV 16 kHz 16-bit (cache a cote du source).
    """
    cache_dir = source.parent / ".mobile_preview"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{source.stem}_16k.wav"
    try:
        src_mtime = source.stat().st_mtime
    except OSError:
        src_mtime = 0.0
    if cached.is_file():
        try:
            if cached.stat().st_mtime >= src_mtime:
                return cached
        except OSError:
            pass
    export_listen_preview_wav(source, cached, sample_rate=16000)
    return cached


def _normalize_fr_phone(raw: str) -> Optional[str]:
    """
    Normalise un numero FR en chiffres (0XXXXXXXXX ou 33XXXXXXXXX).

    @param raw Numero brut.
    @returns Chiffres normalises ou None.
    """
    digits = _digits(raw)
    if not digits:
        return None
    if digits.startswith("0033"):
        digits = "33" + digits[4:]
    if digits.startswith("33") and len(digits) >= 11:
        return "0" + digits[2:]
    if digits.startswith("0") and len(digits) >= 10:
        return digits[:11]
    return digits


@router.get("/voicemails")
async def public_list_voicemails(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    is_read: Optional[bool] = None,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Liste paginee des messages vocaux."""
    _require_token_permission(token, "can_read_voicemails", "Ce token ne peut pas lire les messages vocaux.")
    q = db.query(Voicemail)
    if is_read is not None:
        q = q.filter(Voicemail.is_read.is_(is_read))
    total = q.count()
    rows = q.order_by(Voicemail.created_at.desc()).offset(skip).limit(limit).all()
    items = [VoicemailResponse.model_validate(vm).model_dump() for vm in rows]
    return {"total": int(total), "skip": skip, "limit": limit, "voicemails": items}


@router.get("/voicemails/{voicemail_id}/audio")
async def public_voicemail_audio(
    voicemail_id: int,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    token: ApiPublicToken = Depends(_require_public_token),
):
    """Stream audio WAV d un message vocal."""
    _require_token_permission(token, "can_read_voicemails", "Ce token ne peut pas lire les messages vocaux.")
    vm = db.query(Voicemail).filter(Voicemail.id == voicemail_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="Message vocal introuvable.")
    path = _resolve_voicemail_audio(config, vm.audio_file)
    if not path:
        raise HTTPException(status_code=404, detail="Fichier audio introuvable.")
    try:
        playable = _mobile_voicemail_audio_path(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion audio mobile echouee.") from exc
    return FileResponse(str(playable), media_type="audio/wav", filename=f"vm_{voicemail_id}.wav")


@router.put("/voicemails/{voicemail_id}/read")
async def public_mark_voicemail_read(
    voicemail_id: int,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Marque un message vocal comme lu."""
    _require_token_permission(token, "can_read_voicemails", "Ce token ne peut pas lire les messages vocaux.")
    vm = db.query(Voicemail).filter(Voicemail.id == voicemail_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="Message vocal introuvable.")
    vm.is_read = True
    db.commit()
    return {"ok": True, "id": voicemail_id}


@router.get("/stats")
async def public_stats(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Resume statistiques pour le dashboard mobile."""
    _require_token_permission(token, "can_read_calls", "Ce token ne peut pas lire les appels.")
    today = datetime.utcnow().date()
    calls_today = (
        db.query(func.count(Call.id))
        .filter(func.date(Call.call_time) == today)
        .scalar()
        or 0
    )
    unread = db.query(func.count(Voicemail.id)).filter(Voicemail.is_read.is_(False)).scalar() or 0
    return {"calls_today": int(calls_today), "unread_voicemails": int(unread)}


@router.get("/sync/delta")
async def public_sync_delta(
    since: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """
    Retourne appels et messages vocaux modifies depuis une date ISO8601.

    @param since Horodatage ISO (UTC) ; si absent, retourne les 7 derniers jours.
    """
    _require_token_permission(token, "can_read_calls", "Ce token ne peut pas lire les appels.")
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Parametre since invalide.") from exc
    else:
        since_dt = datetime.utcnow() - timedelta(days=7)

    calls = (
        db.query(Call)
        .filter(Call.call_time >= since_dt)
        .order_by(Call.call_time.desc())
        .limit(500)
        .all()
    )
    vms: List[Voicemail] = []
    if bool(getattr(token, "can_read_voicemails", False)):
        # Toujours renvoyer les messages des 72 dernieres heures pour capter les transcriptions STT tardives.
        vm_since = datetime.utcnow() - timedelta(hours=_VM_DELTA_LOOKBACK_HOURS)
        vms = (
            db.query(Voicemail)
            .filter(Voicemail.created_at >= vm_since)
            .order_by(Voicemail.created_at.desc())
            .limit(500)
            .all()
        )

    return {
        "since": since_dt.isoformat(),
        "server_time": utc_now_naive().isoformat(),
        "calls": [
            {
                "id": c.id,
                "phone_number": c.phone_number,
                "caller_name": c.caller_name,
                "call_time": c.call_time.isoformat() if c.call_time else None,
                "status": c.status,
                "duration": c.duration,
            }
            for c in calls
        ],
        "voicemails": [VoicemailResponse.model_validate(vm).model_dump() for vm in vms],
    }


@router.get("/trusted")
async def public_list_trusted(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Liste des personnes de confiance (whitelist)."""
    _require_token_permission(token, "can_write_trusted", "Ce token ne peut pas gerer les personnes de confiance.")
    rows = db.query(Caller).filter(Caller.is_whitelisted.is_(True)).order_by(Caller.updated_at.desc()).all()
    return {
        "trusted": [
            {
                "phone_number": c.phone_number,
                "name": c.name,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in rows
        ]
    }


@router.post("/trusted/import")
async def public_trusted_import(
    payload: TrustedContactImportRequest,
    db: Session = Depends(get_db),
    block_service: BlockService = Depends(get_block_service),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Import batch de contacts en personnes de confiance."""
    _require_token_permission(token, "can_write_trusted", "Ce token ne peut pas gerer les personnes de confiance.")
    caller_repo = CallerRepository(db)
    imported = 0
    skipped = 0
    for item in payload.contacts:
        normalized = _normalize_fr_phone(item.phone_number)
        if not normalized:
            skipped += 1
            continue
        await block_service.whitelist_caller(normalized)
        caller = caller_repo.get_by_phone_number(normalized)
        if caller and item.name:
            caller_repo.update(caller.id, name=item.name.strip())
        imported += 1
    return {"imported": imported, "skipped": skipped}


@router.delete("/trusted/{phone}")
async def public_trusted_remove(
    phone: str,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """Retire un numero de la liste blanche."""
    _require_token_permission(token, "can_write_trusted", "Ce token ne peut pas gerer les personnes de confiance.")
    normalized = _normalize_fr_phone(phone) or _digits(phone)
    if not normalized:
        raise HTTPException(status_code=400, detail="Numero invalide.")
    caller_repo = CallerRepository(db)
    caller = caller_repo.get_by_phone_number(normalized)
    if not caller:
        raise HTTPException(status_code=404, detail="Appelant introuvable.")
    caller_repo.update(caller.id, is_whitelisted=False)
    return {"ok": True, "phone_number": normalized}


@router.post("/mobile/claim", response_model=MobileClaimResponse)
async def public_mobile_claim(payload: MobileClaimRequest, db: Session = Depends(get_db)) -> MobileClaimResponse:
    """
    Echange un code appairage ephemere contre le token API mobile.

    @param payload Code QR et hint appareil optionnel.
    @returns Token Bearer et URL serveur.
    """
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code requis.")
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    session = (
        db.query(MobilePairingSession)
        .filter(MobilePairingSession.code_hash == code_hash, MobilePairingSession.claimed_at.is_(None))
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Code invalide ou deja utilise. Regenerer le QR.")
    if is_pairing_expired(session.expires_at):
        raise HTTPException(
            status_code=410,
            detail="QR expire (20 min). Regenerer le QR sur la page App mobile.",
        )

    api_token = db.query(ApiPublicToken).filter(ApiPublicToken.id == session.api_token_id).first()
    if not api_token or not api_token.is_active:
        raise HTTPException(status_code=410, detail="Token associe inactif. Regenerer le QR.")

    session.claimed_at = utc_now_naive()
    session.claimed_device_hint = (payload.device_hint or "").strip() or None
    db.commit()

    perms = {
        "can_read_calls": bool(api_token.can_read_calls),
        "can_read_voicemails": bool(getattr(api_token, "can_read_voicemails", False)),
        "can_write_calls": bool(getattr(api_token, "can_write_calls", False)),
        "can_subscribe_realtime": bool(getattr(api_token, "can_subscribe_realtime", False)),
        "can_write_trusted": bool(getattr(api_token, "can_write_trusted", False)),
    }
    return MobileClaimResponse(token=api_token.token, base_url=session.base_url, permissions=perms)


@router.get("/mobile/ping")
async def public_mobile_ping(
    request: Request,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    """
    Test connexion securise pour l app mobile (API + permissions + modem).

    @returns Etat des composants critiques.
    """
    call_manager = getattr(request.app.state, "call_manager", None)
    modem_ok = False
    if call_manager is not None:
        modem = getattr(call_manager, "modem", None)
        modem_ok = bool(modem and getattr(modem, "is_initialized", False))

    return {
        "ok": True,
        "api_ok": True,
        "ws_ok": bool(getattr(token, "can_subscribe_realtime", False)),
        "modem_ok": modem_ok,
        "permissions": {
            "can_read_calls": bool(token.can_read_calls),
            "can_read_voicemails": bool(getattr(token, "can_read_voicemails", False)),
            "can_write_calls": bool(getattr(token, "can_write_calls", False)),
            "can_subscribe_realtime": bool(getattr(token, "can_subscribe_realtime", False)),
            "can_write_trusted": bool(getattr(token, "can_write_trusted", False)),
        },
    }


@router.post("/calls/outgoing/start", response_model=OutgoingCallActionResponse)
async def public_outgoing_start(
    payload: OutgoingCallStartRequest,
    request: Request,
    token: ApiPublicToken = Depends(_require_public_token),
) -> OutgoingCallActionResponse:
    """
    Demarre un appel sortant via token API mobile (LAN).

    @param payload Numero a appeler.
    @returns Identifiant session sortante.
    """
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas initier d appels sortants.")
    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible.")
    if not call_manager.modem.is_initialized:
        raise HTTPException(status_code=503, detail="Modem non initialise.")

    phone = payload.phone_number.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Numero invalide.")

    call = await call_manager.call_service.create_outgoing_call(phone)
    from backend.core.outgoing_session_registry import OutgoingCallSession, outgoing_sessions
    from backend.api.routes.calls import _run_outgoing_call_session, _publish_log
    import asyncio

    session = OutgoingCallSession(call_id=call.id, phone_number=phone)
    outgoing_sessions[call.id] = session
    asyncio.create_task(_publish_log(call.id, phone, "Session sortante mobile"))
    asyncio.create_task(_run_outgoing_call_session(request.app, session))
    return OutgoingCallActionResponse(ok=True, call_id=call.id, message="Appel sortant demarre")


@router.post("/calls/outgoing/{call_id}/dtmf", response_model=OutgoingCallActionResponse)
async def public_outgoing_dtmf(
    call_id: int,
    payload: DtmfRequest,
    request: Request,
    token: ApiPublicToken = Depends(_require_public_token),
) -> OutgoingCallActionResponse:
    """Envoie une touche DTMF pendant un appel sortant mobile."""
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas controler les appels sortants.")
    from backend.core.outgoing_session_registry import outgoing_sessions
    from backend.api.routes.calls import _publish_log

    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible.")
    session = outgoing_sessions.get(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session d appel sortant introuvable.")
    digit = payload.digit.strip()
    ok = await call_manager.modem.send_dtmf(digit)
    if not ok:
        raise HTTPException(status_code=400, detail="Echec envoi DTMF.")
    await _publish_log(call_id, session.phone_number, f"DTMF mobile: {digit}")
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message=f"DTMF {digit} envoye")


@router.post("/calls/outgoing/{call_id}/hangup", response_model=OutgoingCallActionResponse)
async def public_outgoing_hangup(
    call_id: int,
    request: Request,
    token: ApiPublicToken = Depends(_require_public_token),
) -> OutgoingCallActionResponse:
    """Raccroche un appel sortant mobile."""
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas controler les appels sortants.")
    from backend.core.outgoing_session_registry import outgoing_sessions

    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible.")
    session = outgoing_sessions.get(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session d appel sortant introuvable.")
    session.cancel_requested = True
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message="Raccrochage demande")
