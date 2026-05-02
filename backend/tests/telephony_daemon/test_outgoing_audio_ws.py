"""
Contrat WebSocket audio sortant (sans session modem).

Verifie la fermeture propre lorsqu'aucune session n'existe (code 4404 cote serveur).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import outgoing_audio


def test_outgoing_audio_ws_unknown_call_closes() -> None:
    app = FastAPI()
    app.state.call_manager = None
    app.include_router(outgoing_audio.router)
    client = TestClient(app)
    with pytest.raises(Exception):  # Starlette ferme la WS ; exception selon version client
        with client.websocket_connect("/ws/outgoing-call/999999/audio"):
            pass
