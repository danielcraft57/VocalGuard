"""Tests appels sortants API publique mobile."""

from __future__ import annotations


def test_outgoing_start_requires_token(client) -> None:
    r = client.post("/api/v1/public/calls/outgoing/start", json={"phone_number": "0612345678"})
    assert r.status_code == 401


def test_outgoing_start_without_modem(client, auth_headers) -> None:
    """Sans call_manager sur l app test, on attend 503."""
    r = client.post(
        "/api/v1/public/calls/outgoing/start",
        headers=auth_headers,
        json={"phone_number": "0612345678"},
    )
    assert r.status_code == 503


def test_outgoing_start_forbidden_without_permission(client, mobile_token) -> None:
    from backend.database import database as db_module
    from backend.database.models import ApiPublicToken

    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        row = db.query(ApiPublicToken).filter(ApiPublicToken.token == mobile_token).first()
        assert row is not None
        row.can_write_calls = False
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/api/v1/public/calls/outgoing/start",
        headers={"Authorization": f"Bearer {mobile_token}"},
        json={"phone_number": "0612345678"},
    )
    assert r.status_code == 403
