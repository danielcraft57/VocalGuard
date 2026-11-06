"""
Client WebSocket STT node15 (/ws/v1/transcribe).
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable, Optional
from urllib.parse import urlencode

try:
    import websockets
    from websockets.sync.client import connect as ws_connect_sync
except ImportError:
    websockets = None  # type: ignore
    ws_connect_sync = None  # type: ignore

from desktop.prospector.settings import stt_token, stt_ws_url


class SttWsClient:
    """
    Envoie PCM 16 kHz mono et recoit partial/final JSON.

    @param on_partial Callback texte partiel.
    @param on_final Callback texte final.
    """

    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.on_partial = on_partial
        self.on_final = on_final
        self._ws = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = threading.Event()
        self._pcm_queue: asyncio.Queue[bytes] | None = None

    def _build_url(self) -> str:
        params = {"mode": "live"}
        tok = stt_token()
        if tok:
            params["token"] = tok
        base = stt_ws_url()
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{urlencode(params)}"

    async def _run_async(self) -> None:
        if websockets is None:
            return
        url = self._build_url()
        self._pcm_queue = asyncio.Queue()
        try:
            async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
                self._ws = ws
                while not self._stop.is_set():
                    try:
                        pcm = await asyncio.wait_for(self._pcm_queue.get(), timeout=0.2)
                        if pcm:
                            await ws.send(pcm)
                            await ws.send(json.dumps({"op": "transcribe"}))
                    except asyncio.TimeoutError:
                        pass
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.05)
                    except asyncio.TimeoutError:
                        continue
                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    mtype = msg.get("type")
                    text = str(msg.get("text") or "").strip()
                    if not text:
                        continue
                    if mtype == "partial" and self.on_partial:
                        self.on_partial(text)
                    elif mtype == "final" and self.on_final:
                        self.on_final(text)
        except Exception:
            pass
        finally:
            self._ws = None

    def start(self) -> None:
        """Demarre le client en thread."""
        if websockets is None or self._thread is not None:
            return
        self._stop.clear()

        def _target() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            loop.run_until_complete(self._run_async())

        self._thread = threading.Thread(target=_target, name="prospector-stt-ws", daemon=True)
        self._thread.start()

    def push_pcm(self, chunk: bytes) -> None:
        """Enfile du PCM s16le."""
        if not chunk or self._loop is None or self._pcm_queue is None:
            return

        def _put() -> None:
            if self._pcm_queue is not None:
                try:
                    self._pcm_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

        self._loop.call_soon_threadsafe(_put)

    def stop(self) -> None:
        """Arrete le client."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._loop = None
        self._pcm_queue = None

    def commit_final(self) -> None:
        """Demande un final cote serveur."""
        if self._ws is None or self._loop is None:
            return

        async def _send() -> None:
            if self._ws is not None:
                await self._ws.send(json.dumps({"op": "final"}))

        asyncio.run_coroutine_threadsafe(_send(), self._loop)
