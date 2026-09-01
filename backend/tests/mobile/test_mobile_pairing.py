"""Tests appairage mobile QR."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.database import database as db_module
from backend.database.models import MobilePairingSession


def test_create_and_claim_pairing(client, mobile_token) -> None:
    login = client.post("/api/v1/auth/ui/login", json={"password": "test-ui-password"})
    assert login.status_code == 200
    # Session UI suffit (pas besoin de x-admin-token)
    create = client.post(
        "/api/v1/tokens/pairing-sessions",
        json={"api_token_id": 1, "base_url": "https://vocalguard.test"},
    )
    assert create.status_code == 200
    body = create.json()
    code = body["code"]
    assert "vocalguard://pair" in body["qr_uri"]

    claim = client.post("/api/v1/public/mobile/claim", json={"code": code, "device_hint": "pytest"})
    assert claim.status_code == 200
    claimed = claim.json()
    assert claimed["token"] == mobile_token
    assert claimed["permissions"]["can_read_calls"] is True

    again = client.post("/api/v1/public/mobile/claim", json={"code": code})
    assert again.status_code == 404


def test_pairing_without_ui_session_fails(client, mobile_token) -> None:
    """Sans cookie UI et sans x-admin-token correct, pairing refuse."""
    create = client.post(
        "/api/v1/tokens/pairing-sessions",
        json={"api_token_id": 1, "base_url": "https://vocalguard.test"},
    )
    assert create.status_code == 401


def test_claim_expired_code(client, mobile_token) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        import hashlib

        code = "EXPIRED1"
        session = MobilePairingSession(
            code_hash=hashlib.sha256(code.encode()).hexdigest(),
            api_token_id=1,
            base_url="https://x",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        db.add(session)
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/public/mobile/claim", json={"code": "EXPIRED1"})
    assert r.status_code == 410
