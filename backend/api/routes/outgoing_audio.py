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
    - Client -> serveur: micro en PCM s16le ;
      * modem voix serie (USR5637) -> file mic_modem_queue puis VTX half-duplex ;
      * sinon aplay ALSA vers la ligne si dispo, sinon meme file modem.
    """
    session = outgoing_sessions.get(call_id)
    if session is None:
        await websocket.close(code=4404)
        return
    call_manager = getattr(websocket.app.state, "call_manager", None)
    await session_attach_audio_ws(session, websocket)
    use_voice_serial = bool(
        call_manager and getattr(call_manager, "_use_modem_voice_serial", lambda: False)()
    )
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if not data or call_manager is None:
                continue
            # USR5637 / Conexant : jamais aplay (pas de carte ALSA ligne) — file vers VTX.
            if use_voice_serial:
                try:
                    session.mic_modem_queue.put_nowait(data)
                except asyncio.QueueFull:
                    try:
                        _ = session.mic_modem_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        session.mic_modem_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        pass
                continue
            if await session_ensure_mic_aplay(session, call_manager._alsa_play):
                await session_write_mic_pcm(session, data)
            else:
                try:
                    session.mic_modem_queue.put_nowait(data)
                except asyncio.QueueFull:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket audio sortant: {}", exc)
    finally:
        await session_detach_audio_ws(session, websocket)
