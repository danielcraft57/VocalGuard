"""
WebSocket temps réel pour les événements d'appels.

Diffuse les événements du `event_bus` (CALL_INCOMING, CALL_BLOCKED, etc.)
vers les clients frontend afin d'afficher les appels en cours en temps réel.
"""

from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from backend.core.events import Event, event_bus


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


# S'abonner une seule fois à tous les événements
event_bus.subscribe_all(_handle_any_event)


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

