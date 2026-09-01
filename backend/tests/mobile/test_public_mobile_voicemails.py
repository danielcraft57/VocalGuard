"""Tests voicemails API publique mobile."""

from __future__ import annotations


def test_voicemails_list_empty(client, auth_headers) -> None:
    r = client.get("/api/v1/public/voicemails", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_voicemails_unauthorized(client) -> None:
    r = client.get("/api/v1/public/voicemails")
    assert r.status_code == 401
