"""Contrats de montage FastAPI du daemon (sans lancer le lifespan)."""

from __future__ import annotations

from backend.api.routes import outgoing_audio
from backend.core.config import Config
from backend.telephony_daemon.factory import create_telephony_app


def test_create_telephony_app_exposes_health_and_calls_routes() -> None:
    """
    Verifie health + routes sortantes.

    Depuis FastAPI 0.137, app.routes contient des _IncludedRouter sans .path :
    on lit le schema OpenAPI (stable) et le router websocket directement.
    """
    app = create_telephony_app(Config())
    assert getattr(app.state, "is_vocalguard_telephony_daemon", False) is True

    openapi_paths = list(app.openapi().get("paths", {}))
    assert "/health" in openapi_paths, openapi_paths
    assert any("outgoing/start" in p for p in openapi_paths), openapi_paths

    ws_paths = [getattr(r, "path", "") or "" for r in outgoing_audio.router.routes]
    assert any("outgoing-call" in p and "audio" in p for p in ws_paths), ws_paths


def test_create_telephony_app_has_lifespan() -> None:
    app = create_telephony_app(Config())
    assert app.router.lifespan_context is not None
