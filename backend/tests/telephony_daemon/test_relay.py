"""Tests relais HTTP telephony -> API (sans bus, sans modem)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.config import Config
from backend.core.events import Event, EventType
from backend.telephony_daemon.relay import PublicApiEventRelay, make_relay_handler


@pytest.mark.asyncio
async def test_public_api_relay_skips_without_token() -> None:
    relay = PublicApiEventRelay("http://127.0.0.1:8000", "")
    ev = Event(
        event_type=EventType.CALL_SESSION_LOG,
        timestamp=datetime.now(UTC),
        data={"call_id": 1, "message": "x"},
    )
    with patch("backend.telephony_daemon.relay.httpx.AsyncClient") as m:
        await relay(ev)
    m.assert_not_called()


@pytest.mark.asyncio
async def test_public_api_relay_posts_json() -> None:
    relay = PublicApiEventRelay("http://api.test", "secret-token-for-relay")

    class FakeResp:
        status_code = 202
        text = ""

        def json(self) -> dict:
            return {}

    class FakeClient:
        def __init__(self) -> None:
            self.post = AsyncMock(return_value=FakeResp())

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    fake = FakeClient()
    ev = Event(
        event_type=EventType.CALL_OUTGOING_DIALING,
        timestamp=datetime.now(UTC),
        data={"call_id": 7, "phone_number": "+331"},
        source="pytest",
    )

    with patch("backend.telephony_daemon.relay.httpx.AsyncClient", return_value=fake):
        await relay(ev)

    fake.post.assert_awaited_once()
    call_kw = fake.post.await_args
    assert call_kw is not None
    kwargs = call_kw.kwargs
    assert kwargs["headers"]["X-VocalGuard-Internal"] == "secret-token-for-relay"
    body = kwargs["json"]
    assert body["event_type"] == "call.outgoing.dialing"
    assert body["data"]["call_id"] == 7


@pytest.mark.asyncio
async def test_make_relay_handler_same_as_instance_call() -> None:
    c = Config()
    c.telephony_public_api_url = "http://127.0.0.1:9"
    c.telephony_internal_token = "tok"
    h = make_relay_handler(c)
    assert h is not None
    assert hasattr(h, "__call__")


@pytest.mark.asyncio
async def test_public_api_relay_logs_http_error() -> None:
    relay = PublicApiEventRelay("http://api.test", "tok")

    class BadResp:
        status_code = 500
        text = "boom"

    class FakeClient:
        post = AsyncMock(return_value=BadResp())

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    with patch("backend.telephony_daemon.relay.httpx.AsyncClient", return_value=FakeClient()):
        await relay(
            Event(
                event_type=EventType.CALL_SESSION_LOG,
                timestamp=datetime.now(UTC),
                data={"call_id": 1, "message": "m"},
            )
        )


@pytest.mark.asyncio
async def test_public_api_from_config_uses_telephony_urls() -> None:
    c = Config()
    c.telephony_public_api_url = "https://edge.example/vg"
    c.telephony_internal_token = "abc"
    r = PublicApiEventRelay.from_config(c)
    assert r._base == "https://edge.example/vg"
    assert r._token == "abc"
