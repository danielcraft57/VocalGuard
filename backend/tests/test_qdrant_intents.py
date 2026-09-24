"""
Tests client Qdrant intents (HTTP mocke, sans serveur reel).
"""

from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest

from backend.voice import qdrant_intents as qi
from backend.voice.intent_embed import EMBED_DIM


class _FakeResponse:
    """Reponse httpx minimale pour les mocks."""

    def __init__(self, status_code: int = 200, payload: Dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload or "")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> Dict[str, Any]:
        return self._payload


def test_qdrant_base_url_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans QDRANT_URL -> None."""
    monkeypatch.delenv("QDRANT_URL", raising=False)
    assert qi.qdrant_base_url() is None


def test_qdrant_base_url_strip(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL normalisee sans slash final."""
    monkeypatch.setenv("QDRANT_URL", "http://node15.lan:6333/")
    assert qi.qdrant_base_url() == "http://node15.lan:6333"


def test_ensure_collection_already_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collection deja presente -> True sans PUT."""
    calls: list[str] = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            calls.append(f"GET {url}")
            return _FakeResponse(200)

        def put(self, url: str, json=None):
            calls.append(f"PUT {url}")
            return _FakeResponse(200)

    monkeypatch.setattr(qi.httpx, "Client", lambda timeout=10.0: _Client())
    ok = qi.ensure_intents_collection(qdrant_url="http://127.0.0.1:6333")
    assert ok is True
    assert any(c.startswith("GET ") for c in calls)
    assert not any(c.startswith("PUT ") for c in calls)


def test_upsert_embedding_point_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upsert point valide."""
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    monkeypatch.setattr(qi, "ensure_intents_collection", lambda **kwargs: True)

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def put(self, url: str, json=None):
            assert "points" in url
            assert json and "points" in json
            assert len(json["points"][0]["vector"]) == EMBED_DIM
            return _FakeResponse(200)

    monkeypatch.setattr(qi.httpx, "Client", lambda timeout=10.0: _Client())
    ok = qi.upsert_embedding_point(
        point_id=42,
        vector=[0.0] * EMBED_DIM,
        intent_tag="prise_rdv",
        ref_type="pattern",
        ref_id=7,
    )
    assert ok is True


def test_upsert_wrong_dim(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dim incorrecte -> False sans appel HTTP."""
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    ok = qi.upsert_embedding_point(
        point_id=1,
        vector=[0.0, 0.0],
        intent_tag="x",
        ref_type="pattern",
        ref_id=1,
    )
    assert ok is False


def test_fetch_qdrant_status_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans URL -> configured False."""
    monkeypatch.delenv("QDRANT_URL", raising=False)
    status = qi.fetch_qdrant_status()
    assert status["configured"] is False
    assert status["ok"] is False
