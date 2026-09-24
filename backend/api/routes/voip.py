"""
Routes VoIP stub (sans compte SIP) : simulation entrante et etat transport.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from loguru import logger

from backend.api.dependencies import get_call_repository, get_config, get_db
from backend.core.config import Config
from backend.core.events import Event, EventType, event_bus
from backend.core.telephony_transport import VoipTransport
from backend.repositories.call_repository import CallRepository
from backend.services.call_service import CallService
from sqlalchemy.orm import Session

router = APIRouter()


class SimulateIncomingBody(BaseModel):
    """Corps pour simuler une INVITE entrante (tests)."""

    phone_number: str = Field(..., description="Numero appelant (E.164 ou national)")
    caller_name: Optional[str] = Field(default=None, description="Nom CID optionnel")
    auto_answer: bool = Field(
        default=True,
        description="Si True, decroche le stub immediatement apres l'event",
    )


def _call_manager_from_request(request: Request):
    """
    Recupere le CallManager du daemon (app.state).

    @param request Requete FastAPI.
    @returns CallManager ou None.
    """
    return getattr(request.app.state, "call_manager", None)


@router.get("/voip/status")
async def voip_status(request: Request, config: Config = Depends(get_config)) -> dict[str, Any]:
    """
    Etat du backend VoIP / transport courant.

    @returns JSON telephony_backend + health transport.
    """
    cm = _call_manager_from_request(request)
    backend = str(getattr(config, "telephony_backend", "modem") or "modem")
    payload: dict[str, Any] = {
        "telephony_backend": backend,
        "sip_uri_configured": bool(getattr(config, "sip_uri", None)),
        "sip_user_configured": bool(getattr(config, "sip_user", None)),
    }
    if cm is None:
        payload["transport"] = None
        payload["note"] = "CallManager absent (route API hors daemon ?)"
        return payload
    transport = getattr(cm, "transport", None)
    if transport is not None and hasattr(transport, "health_snapshot"):
        payload["transport"] = transport.health_snapshot()
    else:
        payload["transport"] = {"telephony_transport": "unknown"}
    return payload


@router.post("/voip/simulate-incoming")
async def voip_simulate_incoming(
    body: SimulateIncomingBody,
    request: Request,
    db: Session = Depends(get_db),
    config: Config = Depends(get_config),
    call_repo: CallRepository = Depends(get_call_repository),
) -> dict[str, Any]:
    """
    Simule un appel entrant VoIP (sans DID / compte SIP).

    Publie CALL_INCOMING, cree l'appel en base, optionnellement decroche le stub
    pour ouvrir une session PCM loopback.

    @param body Numero + options.
    @returns call_id et etat session.
    """
    _ = call_repo
    cm = _call_manager_from_request(request)
    if cm is None:
        raise HTTPException(
            status_code=503,
            detail="Disponible sur le daemon telephonie uniquement",
        )
    voip = cm.get_voip_transport() if hasattr(cm, "get_voip_transport") else None
    if voip is None or not isinstance(voip, VoipTransport):
        raise HTTPException(
            status_code=400,
            detail=(
                "Backend voip/dual requis (telephony_backend=voip|dual). "
                f"Actuel={getattr(config, 'telephony_backend', 'modem')}"
            ),
        )
    if not voip.is_initialized:
        await voip.start()

    call_service = CallService(db)
    call = await call_service.create_incoming_call(
        body.phone_number,
        caller_name=body.caller_name,
    )
    call_id = int(call.id)
    await event_bus.publish(
        Event(
            event_type=EventType.CALL_INCOMING,
            timestamp=datetime.utcnow(),
            data={
                "call_id": call_id,
                "phone_number": body.phone_number,
                "caller_name": body.caller_name,
                "transport": "voip_stub",
            },
            source="VoipRoute",
        )
    )
    logger.info(
        "VoIP simulate-incoming call_id={} number={}",
        call_id,
        body.phone_number,
    )

    answered = False
    if body.auto_answer:
        answered = await voip.answer()
        if answered:
            await call_service.answer_call(call_id)
            await event_bus.publish(
                Event(
                    event_type=EventType.CALL_ANSWERED,
                    timestamp=datetime.utcnow(),
                    data={
                        "call_id": call_id,
                        "phone_number": body.phone_number,
                        "transport": "voip_stub",
                    },
                    source="VoipRoute",
                )
            )

    return {
        "ok": True,
        "call_id": call_id,
        "phone_number": body.phone_number,
        "answered": answered,
        "transport": voip.health_snapshot(),
    }
