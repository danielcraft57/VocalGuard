"""Contrats de montage FastAPI du daemon (sans lancer le lifespan)."""

from __future__ import annotations

from backend.core.config import Config
from backend.telephony_daemon.factory import create_telephony_app


def test_create_telephony_app_exposes_health_and_calls_routes() -> None:
    app = create_telephony_app(Config())
    paths = [getattr(r, "path", "") or "" for r in app.routes]
    assert "/health" in paths
    assert any(p.endswith("/calls/outgoing/start") for p in paths)
    assert any("outgoing-call" in p and "audio" in p for p in paths)


def test_create_telephony_app_has_lifespan() -> None:
    app = create_telephony_app(Config())
    assert app.router.lifespan_context is not None
