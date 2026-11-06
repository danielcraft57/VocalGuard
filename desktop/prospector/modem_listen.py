"""Thread worker ecoute modem entrante."""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal

from desktop.prospector.call_session import run_incoming_listen_loop
from desktop.prospector.settings import modem_baudrate, modem_com_port


class IncomingListenWorker(QThread):
    """
    Boucle asyncio ecoute RING/CID.

    @signal status Message barre d'etat.
    @signal ring_detected Sonnerie sans CID.
    @signal caller_detected Numero + nom.
    """

    status = Signal(str)
    ring_detected = Signal()
    caller_detected = Signal(str, str)

    def __init__(self, com_port: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.com_port = com_port or modem_com_port() or None
        self._stop = threading.Event()

    def stop(self) -> None:
        """Demande l'arret."""
        self._stop.set()

    def run(self) -> None:
        """Demarre monitor_calls."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def on_ring() -> None:
            self.ring_detected.emit()

        def on_cid(num: str, name: Optional[str]) -> None:
            self.caller_detected.emit(num, name or "")

        try:
            loop.run_until_complete(
                run_incoming_listen_loop(
                    com_port=self.com_port,
                    baudrate=modem_baudrate(),
                    stop_event=self._stop,
                    on_status=lambda m: self.status.emit(m),
                    on_ring=on_ring,
                    on_caller_id=on_cid,
                )
            )
        finally:
            loop.close()
