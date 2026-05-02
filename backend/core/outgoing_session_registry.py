"""
Registre des sessions d'appels sortants (modem) pour la modale web.

Garde l'etat en memoire, les abonnes WebSocket audio, et un processus aplay
optionnel pour envoyer le micro PC vers la ligne (peripherique ALSA).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket


@dataclass
class OutgoingCallSession:
    """Session d'appel sortant suivie pour la modale et le streaming audio."""

    call_id: int
    phone_number: str
    started_monotonic: float = field(default_factory=time.monotonic)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    transcript_parts: list[str] = field(default_factory=list)
    _audio_ws: list[WebSocket] = field(default_factory=list)
    _audio_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    mic_aplay_proc: Optional[asyncio.subprocess.Process] = None
    mic_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    mic_modem_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))


outgoing_sessions: dict[int, OutgoingCallSession] = {}


async def session_attach_audio_ws(session: OutgoingCallSession, websocket: WebSocket) -> None:
    """Enregistre un client WebSocket pour recevoir le PCM ligne -> navigateur."""
    await websocket.accept()
    async with session._audio_lock:
        session._audio_ws.append(websocket)


async def session_detach_audio_ws(session: OutgoingCallSession, websocket: WebSocket) -> None:
    """Retire un client WebSocket audio."""
    async with session._audio_lock:
        if websocket in session._audio_ws:
            session._audio_ws.remove(websocket)


async def session_broadcast_pcm(session: OutgoingCallSession, pcm: bytes) -> None:
    """Envoie un chunk PCM s16le aux ecouteurs connectes (meilleur effort)."""
    if not pcm:
        return
    async with session._audio_lock:
        listeners = list(session._audio_ws)
    dead: list[WebSocket] = []
    for ws in listeners:
        try:
            await ws.send_bytes(pcm)
        except Exception:
            dead.append(ws)
    if dead:
        async with session._audio_lock:
            for ws in dead:
                if ws in session._audio_ws:
                    session._audio_ws.remove(ws)


async def session_stop_mic_aplay(session: OutgoingCallSession) -> None:
    """Termine le processus aplay du micro si actif."""
    async with session.mic_lock:
        proc = session.mic_aplay_proc
        session.mic_aplay_proc = None
    if proc is None:
        return
    try:
        if proc.stdin and not proc.stdin.is_closing():
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


async def session_ensure_mic_aplay(session: OutgoingCallSession, alsa_play_device: str) -> bool:
    """
    Demarre aplay en entree raw (stdin) pour envoyer le micro PC vers la ligne (ALSA modem).

    @param session Session d'appel sortant.
    @param alsa_play_device Peripherique ALSA (ex. meme que lecture IVR).
    @returns True si le processus est pret.
    """
    async with session.mic_lock:
        if session.mic_aplay_proc is not None and session.mic_aplay_proc.returncode is None:
            return True
        try:
            proc = await asyncio.create_subprocess_exec(
                "aplay",
                "-D",
                alsa_play_device,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                "16000",
                "-c",
                "1",
                "-t",
                "raw",
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return False
        session.mic_aplay_proc = proc
        return True


async def session_write_mic_pcm(session: OutgoingCallSession, chunk: bytes) -> None:
    """Ecrit des octets PCM s16le 16 kHz mono vers aplay (micro vers ligne)."""
    if not chunk:
        return
    async with session.mic_lock:
        proc = session.mic_aplay_proc
    if proc is not None and proc.stdin is not None and proc.returncode is None:
        try:
            proc.stdin.write(chunk)
            await proc.stdin.drain()
            return
        except (BrokenPipeError, ConnectionResetError, OSError):
            async with session.mic_lock:
                session.mic_aplay_proc = None
    try:
        session.mic_modem_queue.put_nowait(chunk)
    except asyncio.QueueFull:
        pass
