"""
WebSocket temps réel pour les événements d'appels.

Diffuse les événements du `event_bus` (CALL_INCOMING, CALL_BLOCKED, etc.)
vers les clients frontend afin d'afficher les appels en cours en temps réel.
"""

from typing import TYPE_CHECKING, List, Optional
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Body
from loguru import logger

from backend.core.config import Config
from backend.core.events import Event, EventType, event_bus
from backend.database import database as db_module
from backend.database.models import ApiPublicToken


router = APIRouter()


class RealtimeEventManager:
    """Gère les connexions WebSocket et la diffusion des événements."""

    def __init__(self) -> None:
        self._connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("Client WebSocket connecté ({} total)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
            logger.info("Client WebSocket déconnecté ({} restants)", len(self._connections))

    async def broadcast_event(self, event: Event) -> None:
        """Envoie un événement à tous les clients connectés."""
        if not self._connections:
            return

        payload = {
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "data": event.data,
            "source": event.source,
        }

        disconnected: List[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(payload)
            except Exception as exc:
                logger.warning("Echec d'envoi WebSocket, suppression de la connexion: {}", exc)
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)


manager = RealtimeEventManager()


async def _handle_any_event(event: Event) -> None:
    """Handler global pour relayer tous les événements vers les clients WebSocket."""
    await manager.broadcast_event(event)


_main_realtime_wired = False
_daemon_relay_wired = False


def wire_main_process_realtime() -> None:
    """A appeler une fois au demarrage du processus API principal (pas le telephony_daemon)."""
    global _main_realtime_wired
    if _main_realtime_wired:
        return
    event_bus.subscribe_all(_handle_any_event)
    _main_realtime_wired = True


def wire_telephony_daemon_event_relay(config: "Config") -> None:
    """Relaie tous les events du bus vers l'API principale (WebSocket clients)."""
    global _daemon_relay_wired
    if _daemon_relay_wired:
        return
    from backend.telephony_daemon.relay_wiring import wire_daemon_relay_once

    wire_daemon_relay_once(config)
    _daemon_relay_wired = True


if TYPE_CHECKING:
    from backend.core.config import Config


def _extract_ws_token(websocket: WebSocket) -> Optional[str]:
    """
    Lit le token API depuis query ou header Authorization.

    @param websocket Connexion WebSocket entrante.
    @returns Token brut ou None.
    """
    token = (websocket.query_params.get("token") or "").strip()
    if token:
        return token
    auth = (websocket.headers.get("authorization") or websocket.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _is_local_name(hostname: str) -> bool:
    """True pour la machine de dev (Next :3000 vers API :8000)."""
    return (hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _is_same_origin_ui(websocket: WebSocket) -> bool:
    """
    True si le client est le front VocalGuard.

    Same-origin (front servi par l'API) ou les deux cotes en localhost
    (Next sur :3000, API sur :8000). Sans Origin (scripts), on autorise aussi.

    @param websocket Connexion WebSocket entrante.
    @returns True si l'UI locale peut s'abonner sans token.
    """
    origin = (websocket.headers.get("origin") or "").strip()
    host = (websocket.headers.get("host") or "").strip()
    if not origin:
        return True
    if not host:
        return False
    try:
        parsed = urlparse(origin)
        if parsed.netloc.lower() == host.lower():
            return True
        return _is_local_name(parsed.hostname or "") and _is_local_name(host.split(":")[0])
    except Exception:
        return False


def _validate_ws_api_token(token_value: str) -> bool:
    """
    Verifie token actif avec permission can_subscribe_realtime.

    @param token_value Valeur du token API publique.
    @returns True si le token peut s'abonner au flux realtime.
    """
    session_factory = db_module.SessionLocal
    if session_factory is None:
        return False
    db = session_factory()
    try:
        row = (
            db.query(ApiPublicToken)
            .filter(ApiPublicToken.token == token_value, ApiPublicToken.is_active.is_(True))
            .first()
        )
        if not row:
            return False
        return bool(getattr(row, "can_subscribe_realtime", False))
    finally:
        db.close()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """
    WebSocket temps réel.

    Le client recoit un flux JSON d'evenements appels / voicemail.
    - Front VocalGuard (same-origin) : pas de token requis.
    - Clients externes / mobile : `?token=<api_token>` ou Authorization Bearer
      avec permission can_subscribe_realtime.
    """
    token_value = _extract_ws_token(websocket)
    if token_value:
        if not _validate_ws_api_token(token_value):
            logger.warning("WebSocket /ws/events refuse: token invalide")
            await websocket.close(code=4401)
            return
    elif not _is_same_origin_ui(websocket):
        origin = (websocket.headers.get("origin") or "").strip()
        host = (websocket.headers.get("host") or "").strip()
        logger.warning("WebSocket /ws/events refuse: origine {} hote {}", origin or "-", host or "-")
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        while True:
            # On lit simplement pour garder la connexion ouverte (heartbeats éventuels côté client).
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("Erreur sur la connexion WebSocket: {}", exc)
        manager.disconnect(websocket)


@router.post("/events/osint", status_code=202)
async def publish_osint_event(payload: dict = Body(...)) -> dict:
    """
    Permet à Celery (process séparé) de publier un événement temps réel.
    Le WS `/ws/events` relaie ensuite cet event aux clients.
    """
    event_type_raw = str(payload.get("type") or "").strip()
    if event_type_raw not in (
        EventType.OSINT_PROFILE_COMPLETED.value,
        EventType.OSINT_PROFILE_FAILED.value,
    ):
        return {"accepted": False, "reason": "unknown_type"}

    logger.info("Event OSINT reçu: {}", event_type_raw)
    await event_bus.publish(
        Event(
            event_type=EventType(event_type_raw),
            timestamp=datetime.utcnow(),
            data=dict(payload.get("data") or {}),
            source="CeleryOSINT",
        )
    )
    return {"accepted": True}


@router.post("/events/prospect-phone", status_code=202)
async def publish_prospect_phone_event(payload: dict = Body(...)) -> dict:
    """
    Permet au worker Celery ou a un process distant de pousser la progression enrichissement.
    """
    event_type_raw = str(payload.get("type") or "").strip()
    allowed = (
        EventType.PROSPECT_PHONE_ENRICH_PROGRESS.value,
        EventType.PROSPECT_PHONE_ENRICH_ROW.value,
        EventType.PROSPECT_PHONE_ENRICH_COMPLETED.value,
    )
    if event_type_raw not in allowed:
        return {"accepted": False, "reason": "unknown_type"}

    await event_bus.publish(
        Event(
            event_type=EventType(event_type_raw),
            timestamp=datetime.utcnow(),
            data=dict(payload.get("data") or {}),
            source=str(payload.get("source") or "ProspectPhoneEnrich"),
        )
    )
    return {"accepted": True}
