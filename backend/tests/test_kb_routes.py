"""
Tests routes /api/v1/kb (SQLite + TestClient).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.routes import kb as kb_routes
from backend.database import database as db_module
from backend.database.models import Base
from backend.services import intent_repository as intent_repo


@pytest.fixture()
def kb_client(tmp_path: Path, monkeypatch):
    """App minimale avec router KB et DB SQLite."""
    engine = create_engine(f"sqlite:///{tmp_path / 'kb.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_module.SessionLocal = Session

    root = Path(__file__).resolve().parents[2]
    catalog = intent_repo.load_seed_catalog(
        root / "data" / "intents" / "kb_seed" / "conversation_v1.json"
    )
    db = Session()
    intent_repo.seed_intents_from_catalog(db, catalog, replace=True)
    db.close()

    app = FastAPI()
    app.include_router(kb_routes.router, prefix="/api/v1")

    class _Cfg:
        base_path = root
        stt_service_url = None
        stt_internal_token = None

    app.state.config = _Cfg()
    client = TestClient(app)
    yield client
    db_module.SessionLocal = None


def test_get_intents(kb_client):
    r = kb_client.get("/api/v1/kb/intents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 30
    tags = {i["tag"] for i in body["intents"]}
    assert "contact_email" in tags
    assert "aide_menu" in tags
    assert "has_wav" in body["intents"][0]


def test_listen_voice_missing_wav(kb_client, tmp_path):
    """Sans fichier WAV → 404 clair."""
    kb_client.app.state.config.base_path = tmp_path
    (tmp_path / "ivr_wav").mkdir(parents=True, exist_ok=True)
    r = kb_client.get("/api/v1/kb/intents/remerciements/voice")
    assert r.status_code == 404


def test_intent_predict_local(kb_client):
    r = kb_client.post(
        "/api/v1/kb/intent-predict",
        json={"text": "merci beaucoup", "top_k": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "local"
    assert body["top_predictions"]


def test_patch_intent_response(kb_client):
    r = kb_client.patch(
        "/api/v1/kb/intents/horaires",
        json={"responses": ["Ouvert du lundi au vendredi."]},
    )
    assert r.status_code == 200
    assert r.json()["responses"][0].startswith("Ouvert")


def test_create_and_delete_intent(kb_client):
    """CRUD : creer puis supprimer un intent custom."""
    r = kb_client.post(
        "/api/v1/kb/intents",
        json={
            "tag": "test_chat_crud",
            "patterns": ["phrase de test crud"],
            "responses": ["Reponse de test CRUD."],
            "priority": 42,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tag"] == "test_chat_crud"
    assert body["responses"][0].startswith("Reponse")

    dup = kb_client.post(
        "/api/v1/kb/intents",
        json={"tag": "test_chat_crud", "patterns": ["x"], "responses": ["y"]},
    )
    assert dup.status_code == 400

    d = kb_client.delete("/api/v1/kb/intents/test_chat_crud")
    assert d.status_code == 200
    assert d.json()["deleted"] is True

    missing = kb_client.delete("/api/v1/kb/intents/test_chat_crud")
    assert missing.status_code == 404


def test_kb_chat_reply(kb_client):
    """Tchat : predict + texte de reponse de l'intent."""
    r = kb_client.post(
        "/api/v1/kb/chat",
        json={"text": "merci beaucoup pour votre aide"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["tag"]
    assert body["top_predictions"]


def test_kb_chat_avoids_repeat(kb_client):
    """Deux tours sur bonjour apres salutation → persona, pas le meme catalogue."""
    first = kb_client.post(
        "/api/v1/kb/chat",
        json={
            "text": "bonjour",
            "recent_replies": ["Bonjour, vous etes bien sur la messagerie."],
            "recent_tags": ["salutation"],
            "recent_user_texts": [],
        },
    ).json()
    second = kb_client.post(
        "/api/v1/kb/chat",
        json={
            "text": "bonjour",
            "recent_replies": [
                "Bonjour, vous etes bien sur la messagerie.",
                first["reply"],
            ],
            "recent_tags": ["salutation", first.get("tag") or "salutation"],
            "recent_user_texts": ["bonjour"],
        },
    ).json()
    assert first["reply"]
    assert second["reply"]
    assert first["reply"] != second["reply"]
    assert first.get("persona_reason") == "repeat_hello" or first.get("mood")


def test_predict_node15_down_falls_back(kb_client):
    """Si node15 configure mais KO → local."""
    kb_client.app.state.config.stt_service_url = "http://127.0.0.1:9"

    async def boom(*_a, **_k):
        raise RuntimeError("down")

    with patch.object(
        kb_routes.Node15VoiceClient, "intent_predict", side_effect=boom
    ):
        r = kb_client.post(
            "/api/v1/kb/intent-predict",
            json={"text": "horaires d ouverture"},
        )
    assert r.status_code == 200
    assert r.json()["source"] == "local"
