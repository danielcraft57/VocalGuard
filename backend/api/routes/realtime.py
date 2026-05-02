"""
WebSocket temps réel pour les événements d'appels.

Diffuse les événements du `event_bus` (CALL_INCOMING, CALL_BLOCKED, etc.)
vers les clients frontend afin d'afficher les appels en cours en temps réel.
"""

from typing import TYPE_CHECKING, List
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Body
from loguru import logger

from backend.core.events import Event, EventType, event_bus


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


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    """
    WebSocket temps réel.

    Le client reçoit un flux JSON:
    {
        "type": "call.incoming" | "call.blocked" | ...,
        "timestamp": "...",
        "data": { ... payload specifique ... },
        "source": "CallService" | ...
    }
    """
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

