"""Endpoints API publique dedies a l application mobile."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.api.dependencies import (
    get_block_service,
    get_call_repository,
    get_config,
    get_voicemail_repository,
)
from backend.api.models import (
    CallResponse,
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
    _profile_to_osint_response,
    _proxy_outgoing_to_telephony,
    _safe_recording_path,
    _should_proxy_outgoing_to_daemon,
)
from backend.api.routes.voicemails import _resolve_voicemail_audio
from backend.core.config import Config
from backend.database.database import get_db
from backend.database.models import (
    ApiPublicToken,
    Call,
    Caller,
    MobilePairingSession,
    PhoneNumberProfile,
    Voicemail,
)
from backend.osint.services import PhoneOsintService
from backend.repositories.call_repository import CallRepository
from backend.repositories.caller_repository import CallerRepository
from backend.services.block_service import BlockService
from backend.services.pairing_time import is_pairing_expired, utc_now_naive
from backend.voice.audio_utils import export_listen_preview_wav

router = APIRouter(prefix="/public", tags=["public-mobile"])

# Fenetre de re-sync messages vocaux (transcription STT arrive souvent apres le 1er delta).
_VM_DELTA_LOOKBACK_HOURS = 72


def _outgoing_transport_ready(call_manager) -> bool:
    """Delegue a telephony_transport.outgoing_transport_ready."""
    from backend.core.telephony_transport import outgoing_transport_ready

    return outgoing_transport_ready(call_manager)


def _telephony_public_ws_base(config: Config) -> Optional[str]:
    """
    Base WS audio publiee au mobile (sans chemin /ws/outgoing-call).

    @param config Config app.
    @returns Ex. ws://node14.lan:8090 ou None.
    """
    explicit = (getattr(config, "telephony_public_ws_base", None) or "").strip()
    if not explicit:
        import os

        explicit = (os.environ.get("TELEPHONY_PUBLIC_WS_BASE") or "").strip()
    if explicit:
        u = explicit.rstrip("/")
        if u.startswith("http://"):
            u = "ws://" + u[len("http://") :]
        elif u.startswith("https://"):
            u = "wss://" + u[len("https://") :]
        return u
    daemon = (getattr(config, "telephony_daemon_url", None) or "").strip().rstrip("/")
    if daemon:
        return daemon.replace("https://", "wss://").replace("http://", "ws://")
    return None


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


def _truncate_transcript(text: Optional[str], max_len: int = 4000) -> Optional[str]:
    """
    Tronque une transcription pour le delta liste mobile (assez long pour karaoke).

    @param text Texte brut.
    @param max_len Longueur max.
    @returns Texte tronque ou None.
    """
    if not text:
        return None
    trimmed = text.strip()
    if not trimmed:
        return None
    if len(trimmed) <= max_len:
        return trimmed
    return trimmed[: max_len - 3] + "..."


def _osint_profiles_by_phone(
    db: Session,
    phones: List[str],
) -> dict[str, PhoneNumberProfile]:
    """
    Charge les profils OSINT en base pour une liste de numeros.

    @param db Session SQLAlchemy.
    @param phones Numeros bruts.
    @returns Map phone_number -> PhoneNumberProfile.
    """
    unique = [p for p in set(phones) if p]
    if not unique:
        return {}
    osint_svc = PhoneOsintService(db, Config())
    norms = {p: osint_svc._normalize_number(p) for p in unique}
    norm_values = [n for n in norms.values() if n]
    if not norm_values:
        return {}
    rows = (
        db.query(PhoneNumberProfile)
        .filter(PhoneNumberProfile.normalized_number.in_(norm_values))
        .order_by(
            PhoneNumberProfile.normalized_number,
            desc(PhoneNumberProfile.last_checked_at),
        )
        .all()
    )
    profile_by_norm: dict[str, PhoneNumberProfile] = {}
    for p in rows:
        if p.normalized_number not in profile_by_norm:
            profile_by_norm[p.normalized_number] = p
    out: dict[str, PhoneNumberProfile] = {}
    for phone, norm in norms.items():
        if norm and norm in profile_by_norm:
            out[phone] = profile_by_norm[norm]
    return out


def _osint_light_dict(profile: PhoneNumberProfile, phone_number: str) -> dict:
    """
    Payload OSINT leger pour la liste mobile (offline).

    @param profile Profil en base.
    @param phone_number Numero affiche.
    @returns Dict serialisable.
    """
    full = _profile_to_osint_response(profile, phone_number)
    return {
        "phone_number": full.phone_number,
        "reputation": full.reputation,
        "recommendation": full.recommendation,
        "is_spam": full.is_spam,
        "is_scam": full.is_scam,
        "operator": full.operator,
        "city": full.city,
        "region": full.region,
        "is_company": full.is_company,
        "name": full.name,
        "company_name": full.company_name,
    }


def _call_delta_item(call: Call, profile: Optional[PhoneNumberProfile]) -> dict:
    """
    Serialise un appel pour le delta sync mobile.

    @param call Modele Call.
    @param profile Profil OSINT ou None.
    @returns Dict liste.
    """
    phone = call.phone_number or ""
    osint = _osint_light_dict(profile, phone) if profile and phone else None
    item: dict = {
        "id": call.id,
        "phone_number": call.phone_number,
        "caller_name": call.caller_name,
        "call_time": call.call_time.isoformat() if call.call_time else None,
        "status": call.status,
        "duration": call.duration,
        "audio_file": call.audio_file,
        "transcription": _truncate_transcript(call.transcription),
        "no_message": bool(call.no_message),
        "osint": osint,
    }
    # Cues karaoke pour lecture offline (meme sans GET /calls/{id}).
    cues = getattr(call, "transcription_cues", None)
    if cues:
        item["transcription_cues"] = cues
    return item


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
    phones = [c.phone_number for c in calls if c.phone_number]
    profiles = _osint_profiles_by_phone(db, phones)

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
            _call_delta_item(c, profiles.get(c.phone_number or ""))
            for c in calls
        ],
        "voicemails": [VoicemailResponse.model_validate(vm).model_dump() for vm in vms],
    }


@router.get("/calls/{call_id}", response_model=CallResponse)
async def public_get_call(
    call_id: int,
    db: Session = Depends(get_db),
    call_repo: CallRepository = Depends(get_call_repository),
    token: ApiPublicToken = Depends(_require_public_token),
) -> CallResponse:
    """
    Detail d un appel pour l app mobile (OSINT + cues karaoke via extra_data).

    @param call_id Identifiant appel.
    @returns CallResponse complet.
    """
    _require_token_permission(token, "can_read_calls", "Ce token ne peut pas lire les appels.")
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel introuvable.")

    data = CallResponse.model_validate(call).model_dump()
    # Garantir les cues karaoke meme si la serialisation omet la property extra_data.
    if not data.get("extra_data") and getattr(call, "transcription_cues", None) is not None:
        data["extra_data"] = {"transcription_cues": call.transcription_cues}
    elif isinstance(data.get("extra_data"), dict) and "transcription_cues" not in data["extra_data"]:
        if getattr(call, "transcription_cues", None) is not None:
            data["extra_data"] = {
                **data["extra_data"],
                "transcription_cues": call.transcription_cues,
            }
    if call.phone_number:
        profiles = _osint_profiles_by_phone(db, [call.phone_number])
        profile = profiles.get(call.phone_number)
        data["osint"] = (
            _profile_to_osint_response(profile, call.phone_number) if profile else None
        )
    else:
        data["osint"] = None
    return CallResponse(**data)


@router.get("/calls/{call_id}/recording")
async def public_call_recording(
    call_id: int,
    call_repo: CallRepository = Depends(get_call_repository),
    config: Config = Depends(get_config),
    token: ApiPublicToken = Depends(_require_public_token),
):
    """
    Stream WAV d un enregistrement d appel (format lisible mobile / web).

    @param call_id Identifiant appel.
    """
    _require_token_permission(token, "can_read_calls", "Ce token ne peut pas lire les appels.")
    call = call_repo.get_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Appel introuvable.")

    path = _safe_recording_path(config, call.audio_file)
    if not path:
        raise HTTPException(status_code=404, detail="Enregistrement indisponible.")

    try:
        playable = _mobile_voicemail_audio_path(path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Conversion audio mobile echouee.") from exc
    return FileResponse(
        str(playable),
        media_type="audio/wav",
        filename=f"call_{call_id}.wav",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=60",
        },
    )


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
    config: Config = Depends(get_config),
) -> dict:
    """
    Test connexion securise pour l app mobile (API + permissions + transport).

    @returns Etat des composants critiques + base WS telephonie.
    """
    _ = db
    call_manager = getattr(request.app.state, "call_manager", None)
    modem_ok = False
    transport_ok = False
    backend = str(getattr(config, "telephony_backend", "modem") or "modem")
    if call_manager is not None:
        modem = getattr(call_manager, "modem", None)
        modem_ok = bool(modem and getattr(modem, "is_initialized", False))
        transport = getattr(call_manager, "transport", None)
        transport_ok = bool(transport and getattr(transport, "is_initialized", False))
        backend = str(
            getattr(getattr(call_manager, "telephony_backend", None), "value", None)
            or backend
        )

    return {
        "ok": True,
        "api_ok": True,
        "ws_ok": bool(getattr(token, "can_subscribe_realtime", False)),
        "modem_ok": modem_ok,
        "transport_ok": transport_ok or modem_ok,
        "telephony_backend": backend,
        "telephony_ws_base": _telephony_public_ws_base(config),
        "outgoing_ready": _outgoing_transport_ready(call_manager)
        if call_manager is not None
        else False,
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
    config: Config = Depends(get_config),
) -> OutgoingCallActionResponse:
    """
    Demarre un appel sortant via token API mobile (LAN).

    Proxifie vers le daemon telephonie si USE_TELEPHONY_DAEMON (comme le dialer web),
    pour que le chemin modem / VoIP tourne la ou le transport est actif.

    @param payload Numero a appeler.
    @returns Identifiant session sortante.
    """
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas initier d appels sortants.")
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            "/api/v1/calls/outgoing/start",
            {"phone_number": payload.phone_number},
        )

    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible.")
    if not _outgoing_transport_ready(call_manager):
        raise HTTPException(
            status_code=503,
            detail="Transport telephonie non pret (modem / VoIP stub).",
        )

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
    config: Config = Depends(get_config),
) -> OutgoingCallActionResponse:
    """Envoie une touche DTMF pendant un appel sortant mobile."""
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas controler les appels sortants.")
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            f"/api/v1/calls/outgoing/{call_id}/dtmf",
            {"digit": payload.digit},
        )

    from backend.core.outgoing_session_registry import outgoing_sessions
    from backend.api.routes.calls import _publish_log
    from backend.core.telephony_transport import TelephonyBackend

    call_manager = getattr(request.app.state, "call_manager", None)
    if call_manager is None:
        raise HTTPException(status_code=503, detail="Call manager indisponible.")
    session = outgoing_sessions.get(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session d appel sortant introuvable.")
    digit = payload.digit.strip()
    backend = getattr(call_manager, "telephony_backend", None)
    ok = False
    if backend in (TelephonyBackend.VOIP, TelephonyBackend.DUAL):
        transport = getattr(call_manager, "transport", None)
        if transport is not None:
            ok = bool(await transport.send_dtmf(digit))
    if not ok:
        ok = bool(await call_manager.modem.send_dtmf(digit))
    if not ok:
        raise HTTPException(status_code=400, detail="Echec envoi DTMF.")
    await _publish_log(call_id, session.phone_number, f"DTMF mobile: {digit}")
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message=f"DTMF {digit} envoye")


@router.post("/calls/outgoing/{call_id}/hangup", response_model=OutgoingCallActionResponse)
async def public_outgoing_hangup(
    call_id: int,
    request: Request,
    token: ApiPublicToken = Depends(_require_public_token),
    config: Config = Depends(get_config),
) -> OutgoingCallActionResponse:
    """Raccroche un appel sortant mobile."""
    _require_token_permission(token, "can_write_calls", "Ce token ne peut pas controler les appels sortants.")
    if _should_proxy_outgoing_to_daemon(config, request):
        return await _proxy_outgoing_to_telephony(
            request,
            config,
            f"/api/v1/calls/outgoing/{call_id}/hangup",
            {},
        )

    from backend.core.outgoing_session_registry import outgoing_sessions
    from backend.api.routes.calls import _publish_log
    import asyncio

    call_manager = getattr(request.app.state, "call_manager", None)
    session = outgoing_sessions.get(call_id)
    if session is None:
        return OutgoingCallActionResponse(
            ok=True, call_id=call_id, message="Session deja terminee"
        )
    asyncio.create_task(
        _publish_log(call_id, session.phone_number, "Raccrochage demande depuis mobile")
    )
    session.stop_event.set()
    if call_manager is not None and getattr(call_manager, "modem", None) is not None:
        call_manager.modem._voice_abort = True
    return OutgoingCallActionResponse(ok=True, call_id=call_id, message="Raccrochage demande")

