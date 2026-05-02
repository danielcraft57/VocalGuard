"""
Ingestion interne des evenements emis par le service telephony_daemon (vers /ws/events).
"""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.api.dependencies import get_config
from backend.core.config import Config
from backend.core.events import Event, EventType
from backend.api.routes.realtime import manager

router = APIRouter(prefix="/internal", tags=["internal-telephony"])


class TelephonyEventPayload(BaseModel):
    event_type: str
    timestamp: str
    data: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


@router.post("/telephony-events", status_code=202)
async def ingest_telephony_event(
    payload: TelephonyEventPayload = Body(...),
    x_vocalguard_internal: Optional[str] = Header(None, alias="X-VocalGuard-Internal"),
    config: Config = Depends(get_config),
):
    """
    Recoit un event serialise depuis telephony_daemon et le diffuse aux WebSocket /ws/events.
    """
    expected = (config.telephony_internal_token or "").strip()
    if not expected or (x_vocalguard_internal or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Non autorise")

    try:
        et = EventType(payload.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="event_type inconnu")

    try:
        ts = datetime.fromisoformat(payload.timestamp.replace("Z", "+00:00"))
    except Exception:
        ts = datetime.utcnow()

    event = Event(
        event_type=et,
        timestamp=ts,
        data=dict(payload.data or {}),
        source=payload.source or "TelephonyDaemon",
    )
    await manager.broadcast_event(event)
    return {"accepted": True}
