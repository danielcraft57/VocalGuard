"""Tests endpoint ping mobile."""

from __future__ import annotations


def test_mobile_ping_ok(client, auth_headers) -> None:
    r = client.get("/api/v1/public/mobile/ping", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["api_ok"] is True
    assert body["permissions"]["can_subscribe_realtime"] is True


def test_mobile_ping_unauthorized(client) -> None:
    r = client.get("/api/v1/public/mobile/ping")
    assert r.status_code == 401
