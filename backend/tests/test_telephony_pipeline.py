"""
Tests relais appels sortants / daemon telephony (sans modem reel).

Lancer sur le serveur apres deploy :
  cd /opt/vocalguard && source venv/bin/activate && pytest backend/tests/test_telephony_pipeline.py backend/tests/telephony_daemon -q
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.dependencies import get_config
from backend.api.routes.internal_telephony import router as internal_telephony_router
from backend.core.config import Config


def _make_config(token: str = "test-internal-token-32chars-minimum") -> Config:
    c = Config()
    c.telephony_internal_token = token
    return c


@pytest.fixture()
def internal_app() -> TestClient:
    app = FastAPI()
    app.include_router(internal_telephony_router, prefix="/api/v1")

    def cfg() -> Config:
        return _make_config()

    app.dependency_overrides[get_config] = cfg
    return TestClient(app)


def test_internal_telephony_rejects_missing_token(internal_app: TestClient) -> None:
    r = internal_app.post(
        "/api/v1/internal/telephony-events",
        json={
            "event_type": "call.session.log",
            "timestamp": "2026-05-02T12:00:00",
            "data": {"call_id": 1, "phone_number": "0", "message": "x", "level": "info"},
        },
    )
    assert r.status_code == 401


def test_internal_telephony_rejects_bad_token(internal_app: TestClient) -> None:
    r = internal_app.post(
        "/api/v1/internal/telephony-events",
        headers={"X-VocalGuard-Internal": "wrong"},
        json={
            "event_type": "call.session.log",
            "timestamp": "2026-05-02T12:00:00",
            "data": {"call_id": 1, "phone_number": "0", "message": "x", "level": "info"},
        },
    )
    assert r.status_code == 401


def test_internal_telephony_rejects_unknown_event_type(internal_app: TestClient) -> None:
    r = internal_app.post(
        "/api/v1/internal/telephony-events",
        headers={"X-VocalGuard-Internal": "test-internal-token-32chars-minimum"},
        json={
            "event_type": "not.a.real.event",
            "timestamp": "2026-05-02T12:00:00",
            "data": {},
        },
    )
    assert r.status_code == 400


def _minimal_request_scope() -> dict:
    app = SimpleNamespace(state=SimpleNamespace(telephony_daemon_url="http://127.0.0.1:8090"))
    return {
        "type": "http",
        "method": "POST",
        "path": "/x",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
        "app": app,
    }


@pytest.mark.asyncio
async def test_outgoing_proxy_posts_to_daemon_url() -> None:
    """Le mode USE_TELEPHONY_DAEMON proxifie vers TELEPHONY_DAEMON_URL (httpx)."""
    from backend.api.routes.calls import _proxy_outgoing_to_telephony
    from fastapi import Request

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {"ok": True, "call_id": 99, "message": "proxied"}

    class FakeClient:
        async def post(self, *args, **kwargs):
            assert "/api/v1/calls/outgoing/start" in (args[0] if args else kwargs.get("url", ""))
            return FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    req = Request(scope=_minimal_request_scope())
    cfg = _make_config()
    cfg.use_telephony_daemon = True
    cfg.telephony_daemon_url = "http://127.0.0.1:8090"

    with patch("backend.api.routes.calls.httpx.AsyncClient", return_value=FakeClient()):
        out = await _proxy_outgoing_to_telephony(req, cfg, "/api/v1/calls/outgoing/start", {"phone_number": "+331"})
    assert out.ok is True
    assert out.call_id == 99
    assert out.message == "proxied"


@pytest.mark.asyncio
async def test_outgoing_proxy_raises_on_connection_error() -> None:
    from backend.api.routes.calls import _proxy_outgoing_to_telephony
    from fastapi import HTTPException, Request
    import httpx

    class BoomClient:
        async def post(self, *a, **k):
            raise httpx.ConnectError("refused", request=None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    req = Request(scope=_minimal_request_scope())
    cfg = _make_config()
    cfg.use_telephony_daemon = True

    with patch("backend.api.routes.calls.httpx.AsyncClient", return_value=BoomClient()):
        with pytest.raises(HTTPException) as ei:
            await _proxy_outgoing_to_telephony(req, cfg, "/api/v1/calls/outgoing/start", {})
    assert ei.value.status_code == 502


def test_internal_telephony_accepts_valid_event(internal_app: TestClient) -> None:
    with patch("backend.api.routes.internal_telephony.manager.broadcast_event", new_callable=AsyncMock) as m:
        r = internal_app.post(
            "/api/v1/internal/telephony-events",
            headers={"X-VocalGuard-Internal": "test-internal-token-32chars-minimum"},
            json={
                "event_type": "call.outgoing.dialing",
                "timestamp": "2026-05-02T12:00:00Z",
                "data": {"call_id": 5, "phone_number": "+33987654321"},
                "source": "pytest",
            },
        )
    assert r.status_code == 202
    assert r.json().get("accepted") is True
    m.assert_awaited_once()
