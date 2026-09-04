"""
Tests API sessions tchatche KB.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.routes import kb as kb_routes
from backend.database import database as db_module
from backend.database.models import Base


@pytest.fixture()
def kb_client(tmp_path: Path):
    """App minimale KB + SQLite."""
    engine = create_engine(f"sqlite:///{tmp_path / 'kb_chat.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_module.SessionLocal = Session

    app = FastAPI()
    app.include_router(kb_routes.router, prefix="/api/v1")

    class _Cfg:
        base_path = Path(__file__).resolve().parents[2]
        stt_service_url = None
        stt_internal_token = None

    app.state.config = _Cfg()
    client = TestClient(app)
    yield client
    db_module.SessionLocal = None


def test_chat_session_crud(kb_client):
    payload = {
        "id": "s-test-1",
        "title": "Test chat",
        "messages": [
            {"id": "welcome", "role": "bot", "text": "Bonjour"},
            {"id": "u1", "role": "user", "text": "bonjour"},
        ],
        "recentReplies": ["Bonjour"],
        "recentTags": ["salutation"],
        "recentUserTexts": ["bonjour"],
    }
    r = kb_client.put("/api/v1/kb/chats/s-test-1", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Test chat"

    listed = kb_client.get("/api/v1/kb/chats")
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    got = kb_client.get("/api/v1/kb/chats/s-test-1")
    assert got.status_code == 200
    assert got.json()["messages"][1]["text"] == "bonjour"

    deleted = kb_client.delete("/api/v1/kb/chats/s-test-1")
    assert deleted.status_code == 200
    assert kb_client.get("/api/v1/kb/chats/s-test-1").status_code == 404


def test_chat_import(kb_client):
    r = kb_client.post(
        "/api/v1/kb/chats/import",
        json={
            "sessions": [
                {
                    "id": "s-imp-1",
                    "title": "Import",
                    "messages": [{"id": "w", "role": "bot", "text": "Hi"}],
                    "recentReplies": [],
                    "recentTags": [],
                    "recentUserTexts": [],
                }
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1
