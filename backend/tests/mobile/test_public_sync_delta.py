"""Tests sync delta mobile."""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.database import database as db_module
from backend.database.models import Call, PhoneNumberProfile


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
                audio_file="recordings/call_in_test.wav",
                transcription="Bonjour ceci est un test de transcription assez long pour tronquer",
                no_message=False,
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
    call = next(c for c in body["calls"] if c["phone_number"] == "0100000000")
    assert call["audio_file"] == "recordings/call_in_test.wav"
    assert call["transcription"]
    assert call["no_message"] is False
    assert "osint" in call
    assert len(call["transcription"]) > 20


def test_sync_delta_includes_osint(client, auth_headers) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        phone = "0612345678"
        db.add(
            PhoneNumberProfile(
                phone_number=phone,
                normalized_number="+33612345678",
                reputation="high",
                company_name="DanielCraft",
                operator="Orange",
                city="Paris",
                last_checked_at=datetime.utcnow(),
            )
        )
        db.add(
            Call(
                phone_number=phone,
                caller_name=None,
                call_time=datetime.utcnow(),
                status="missed",
                duration=0,
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/public/sync/delta", headers=auth_headers)
    assert r.status_code == 200
    call = next(c for c in r.json()["calls"] if c["phone_number"] == "0612345678")
    assert call["osint"] is not None
    assert call["osint"]["company_name"] == "DanielCraft"
    assert call["osint"]["reputation"] == "high"
    assert call["osint"]["operator"] == "Orange"
    assert "recommendation" in call["osint"]


def test_sync_delta_includes_transcription_cues(client, auth_headers) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    try:
        db.add(
            Call(
                phone_number="0677001122",
                caller_name=None,
                call_time=datetime.utcnow(),
                status="answered",
                duration=14,
                transcription="Voila, voila, c est Louis.",
                transcription_cues=[
                    {
                        "start": 0.0,
                        "end": 2.0,
                        "words": [
                            {"text": "Voila,", "start": 0.0, "end": 0.5},
                            {"text": "voila,", "start": 0.5, "end": 1.0},
                            {"text": "c", "start": 1.0, "end": 1.2},
                            {"text": "est", "start": 1.2, "end": 1.5},
                            {"text": "Louis.", "start": 1.5, "end": 2.0},
                        ],
                    }
                ],
            )
        )
        db.commit()
    finally:
        db.close()

    r = client.get("/api/v1/public/sync/delta", headers=auth_headers)
    assert r.status_code == 200
    call = next(c for c in r.json()["calls"] if c["phone_number"] == "0677001122")
    assert call["transcription"] == "Voila, voila, c est Louis."
    assert isinstance(call.get("transcription_cues"), list)
    assert len(call["transcription_cues"]) == 1


def test_public_get_call_detail(client, auth_headers) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    call_id = None
    try:
        row = Call(
            phone_number="0699887766",
            caller_name="Alice",
            call_time=datetime.utcnow(),
            status="answered",
            duration=42,
            transcription="Bonjour Alice",
            transcription_cues=[
                {
                    "start": 0.0,
                    "end": 1.5,
                    "words": [
                        {"text": "Bonjour", "start": 0.0, "end": 0.7},
                        {"text": "Alice", "start": 0.7, "end": 1.5},
                    ],
                }
            ],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        call_id = row.id
    finally:
        db.close()

    r = client.get(f"/api/v1/public/calls/{call_id}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == call_id
    assert body["transcription"] == "Bonjour Alice"
    assert body["extra_data"] is not None
    assert "transcription_cues" in body["extra_data"]


def test_public_call_recording_missing(client, auth_headers) -> None:
    assert db_module.SessionLocal is not None
    db = db_module.SessionLocal()
    call_id = None
    try:
        row = Call(
            phone_number="0600000001",
            call_time=datetime.utcnow(),
            status="missed",
            audio_file=None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        call_id = row.id
    finally:
        db.close()

    r = client.get(f"/api/v1/public/calls/{call_id}/recording", headers=auth_headers)
    assert r.status_code == 404
