"""Contrats de montage FastAPI du daemon (sans lancer le lifespan)."""

from __future__ import annotations

from backend.core.config import Config
from backend.telephony_daemon.factory import create_telephony_app


def _collect_paths(routes: list) -> list[str]:
    """
    Recupere tous les chemins, y compris sous-routeurs (Starlette/FastAPI recent).

    Sur certaines versions, include_router pose un Mount a path vide : les routes
    filles ne sont pas visibles dans app.routes sans parcours recursif.
    """
    out: list[str] = []
    for route in routes:
        path = getattr(route, "path", None) or ""
        if path:
            out.append(path)
        nested = getattr(route, "routes", None)
        if nested:
            out.extend(_collect_paths(list(nested)))
    return out


def test_create_telephony_app_exposes_health_and_calls_routes() -> None:
    app = create_telephony_app(Config())
    assert getattr(app.state, "is_vocalguard_telephony_daemon", False) is True
    paths = _collect_paths(list(app.routes))
    assert "/health" in paths, paths
    assert any("outgoing/start" in p for p in paths), paths
    assert any("outgoing-call" in p and "audio" in p for p in paths), paths


def test_create_telephony_app_has_lifespan() -> None:
    app = create_telephony_app(Config())
    assert app.router.lifespan_context is not None
