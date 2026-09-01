"""Tests import personnes de confiance."""

from __future__ import annotations

from backend.database import database as db_module
from backend.database.models import Caller


def test_trusted_import_and_delete(client, auth_headers) -> None:
    payload = {
        "contacts": [
            {"name": "Alice", "phone_number": "+33 6 12 34 56 78"},
            {"name": "Bob", "phone_number": "06 98 76 54 32"},
        ]
    }
    r = client.post("/api/v1/public/trusted/import", headers=auth_headers, json=payload)
    assert r.status_code == 200
    assert r.json()["imported"] == 2

    listing = client.get("/api/v1/public/trusted", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()["trusted"]) >= 2

    delete = client.delete("/api/v1/public/trusted/0612345678", headers=auth_headers)
    assert delete.status_code == 200

    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        caller = db.query(Caller).filter(Caller.phone_number == "0612345678").first()
        assert caller is not None
        assert caller.is_whitelisted is False
    finally:
        db.close()
