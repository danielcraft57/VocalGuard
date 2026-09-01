"""Tests authentification UI web."""

from __future__ import annotations


def test_ui_login_ok(client) -> None:
    r = client.post("/api/v1/auth/ui/login", json={"password": "test-ui-password"})
    assert r.status_code == 200
    assert r.cookies.get("vg_ui_session")


def test_ui_login_bad_password(client) -> None:
    r = client.post("/api/v1/auth/ui/login", json={"password": "wrong"})
    assert r.status_code == 401


def test_internal_api_blocked_without_session(client) -> None:
    r = client.get("/api/v1/tokens", headers={"x-admin-token": "admin-test-token"})
    assert r.status_code == 401


def test_internal_api_ok_with_session(client) -> None:
    login = client.post("/api/v1/auth/ui/login", json={"password": "test-ui-password"})
    assert login.status_code == 200
    r = client.get("/api/v1/tokens", headers={"x-admin-token": "admin-test-token"})
    assert r.status_code == 200


def test_public_api_exempt_from_ui_auth(client, auth_headers) -> None:
    r = client.get("/api/v1/public/mobile/ping", headers=auth_headers)
    assert r.status_code == 200
