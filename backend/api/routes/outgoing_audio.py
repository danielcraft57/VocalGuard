"""
WebSocket audio pour appels sortants (modem / ALSA).

Peut etre monte sur l'API principale ou sur le service telephony_daemon uniquement.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from backend.core.outgoing_session_registry import (
    outgoing_sessions,
    session_attach_audio_ws,
    session_detach_audio_ws,
    session_ensure_mic_aplay,
    session_write_mic_pcm,
)

router = APIRouter()


@router.websocket("/ws/outgoing-call/{call_id}/audio")
async def websocket_outgoing_call_audio(websocket: WebSocket, call_id: int) -> None:
    """
    Audio bidirectionnel pour appel sortant (best effort).

    - Serveur -> client: PCM s16le 16 kHz (arecord si carte capture, sinon flux AT+VRX via modem).
    - Client -> serveur: micro en PCM s16le ; aplay vers la ligne si ALSA, sinon file vers VTX (rafales).
    """
    session = outgoing_sessions.get(call_id)
    if session is None:
        await websocket.close(code=4404)
        return
    call_manager = getattr(websocket.app.state, "call_manager", None)
    await session_attach_audio_ws(session, websocket)
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data and call_manager:
                if await session_ensure_mic_aplay(session, call_manager._alsa_play):
                    await session_write_mic_pcm(session, data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket audio sortant: {}", exc)
    finally:
        await session_detach_audio_ws(session, websocket)
