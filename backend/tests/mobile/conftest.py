"""Fixtures tests API mobile."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.middleware.ui_auth import UiAuthMiddleware
from backend.api.routes import auth_ui, public_api, public_mobile, realtime, tokens
from backend.core.config import Config
from backend.database import database as db_module
from backend.database.models import ApiPublicToken


@pytest.fixture()
def mobile_db_url() -> Generator[str, None, None]:
    """Fichier SQLite unique par test."""
    path = Path(__file__).resolve().parent / f"_pytest_{uuid.uuid4().hex}.db"
    url = f"sqlite:///{path.as_posix()}"
    yield url
    db_module.SessionLocal = None
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


@pytest.fixture()
def mobile_app(mobile_db_url: str, monkeypatch) -> Generator[FastAPI, None, None]:
    """Application FastAPI minimale pour tests mobile (sans modem)."""
    monkeypatch.setenv("VG_UI_PASSWORD", "test-ui-password")
    monkeypatch.setenv("API_PUBLIC_ADMIN_TOKEN", "admin-test-token")
    monkeypatch.setenv("VG_ENV", "test")

    asyncio.run(db_module.init_database(mobile_db_url))

    config = Config()
    app = FastAPI()
    app.add_middleware(UiAuthMiddleware, config=config)
    app.include_router(public_api.router, prefix="/api/v1")
    app.include_router(public_mobile.router, prefix="/api/v1")
    app.include_router(tokens.router, prefix="/api/v1")
    app.include_router(auth_ui.router, prefix="/api/v1")
    app.include_router(realtime.router)
    realtime.wire_main_process_realtime()
    yield app


@pytest.fixture()
def client(mobile_app: FastAPI) -> TestClient:
    """Client HTTP de test."""
    return TestClient(mobile_app)


@pytest.fixture()
def mobile_token(client: TestClient) -> str:
    """Cree un token API mobile complet en base."""
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        row = ApiPublicToken(
            name="Mobile test",
            app_url="http://test",
            token="mobile-test-token-abc",
            is_active=True,
            can_read_calls=True,
            can_read_voicemails=True,
            can_write_calls=True,
            can_subscribe_realtime=True,
            can_write_trusted=True,
        )
        db.add(row)
        db.commit()
    finally:
        db.close()
    return "mobile-test-token-abc"


@pytest.fixture()
def auth_headers(mobile_token: str) -> dict:
    """Headers Bearer pour API publique mobile."""
    return {"Authorization": f"Bearer {mobile_token}"}
