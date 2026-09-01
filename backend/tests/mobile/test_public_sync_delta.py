"""Tests sync delta mobile."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.database import database as db_module
from backend.database.models import Call


def test_sync_delta_since(client, auth_headers) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        db.add(
            Call(
                phone_number="0100000000",
                caller_name="Test",
                call_time=datetime.utcnow(),
                status="completed",
            )
        )
        db.commit()
    finally:
        db.close()

    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    r = client.get(f"/api/v1/public/sync/delta?since={since}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["calls"]) >= 1
