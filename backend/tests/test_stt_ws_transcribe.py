"""
Tests du WebSocket STT node15 (Whisper mocke).

On verifie le contrat : auth, partiel, final, fenetre, reset, audio trop court.
Le modele n'est pas charge.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.stt_service import ws_transcribe
from backend.stt_service.ws_transcribe import PcmWindow


def _app() -> FastAPI:
    """Mini app sans lifespan (pas de chargement Whisper)."""
    app = FastAPI()
    app.add_api_websocket_route("/ws/v1/transcribe", ws_transcribe.websocket_transcribe)
    return app


def _pcm(seconds: float) -> bytes:
    """PCM silencieux de la duree demandee (16 kHz, 16-bit)."""
    return b"\x00\x01" * int(ws_transcribe.BYTES_PER_SEC * seconds / 2)


@pytest.fixture
def fake_whisper(monkeypatch: pytest.MonkeyPatch):
    """
    Remplace transcribe_pcm16 par un faux qui note la taille et le mode.

    @returns Liste des appels (len, fast).
    """
    calls: list[dict[str, Any]] = []

    def _fake(pcm: bytes, sample_rate: int = 16000, *, fast: bool = False) -> str:
        calls.append({"nbytes": len(pcm), "rate": sample_rate, "fast": fast})
        return "bonjour" if fast else "bonjour madame"

    monkeypatch.setattr(ws_transcribe.stt_engine, "transcribe_pcm16", _fake)
    monkeypatch.setattr(ws_transcribe.stt_engine, "engine_name", lambda: "whisper")
    monkeypatch.setattr(
        ws_transcribe.stt_engine,
        "last_cues",
        lambda: [{"text": "bonjour madame", "start": 0.0, "end": 1.0}],
    )
    monkeypatch.delenv("STT_INTERNAL_TOKEN", raising=False)
    return calls


def test_pcm_window_keeps_tail_and_odd_byte() -> None:
    """Le buffer jette le debut et recolle un octet coupe entre deux trames."""
    window = PcmWindow(max_sec=1.0)
    window.append(b"\x01")
    window.append(b"\x02" + (b"\x03\x04" * 20000))
    assert len(window) == ws_transcribe.BYTES_PER_SEC
    snap = window.snapshot(0.25)
    assert len(snap) == int(0.25 * ws_transcribe.BYTES_PER_SEC)
    window.clear()
    assert len(window) == 0
    assert window.snapshot(None) == b""


def test_parse_client_op_accepts_partial_alias() -> None:
    """L'alias partial vaut transcribe."""
    assert ws_transcribe.parse_client_op('{"op":"partial"}') == "transcribe"
    with pytest.raises(ValueError):
        ws_transcribe.parse_client_op('{"op":"nope"}')


def test_ws_ready_partial_and_final(fake_whisper) -> None:
    """Une session recoit ready, un partiel rapide, puis un final avec cues."""
    client = TestClient(_app())
    with client.websocket_connect("/ws/v1/transcribe?mode=live&window_sec=1") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["engine"] == "whisper"
        assert ready["window_sec"] == 1.0

        ws.send_bytes(_pcm(2.0))
        ws.send_text(json.dumps({"op": "transcribe"}))
        partial = ws.receive_json()
        assert partial["type"] == "partial"
        assert partial["text"] == "bonjour"
        assert partial["cues"] == []
        assert partial["bytes_pcm"] == ws_transcribe.BYTES_PER_SEC
        assert partial["buffered"] == 2 * ws_transcribe.BYTES_PER_SEC

        ws.send_text(json.dumps({"op": "final"}))
        final = ws.receive_json()
        assert final["type"] == "final"
        assert final["text"] == "bonjour madame"
        assert final["cues"][0]["text"] == "bonjour madame"
        assert final["bytes_pcm"] == 2 * ws_transcribe.BYTES_PER_SEC

    assert fake_whisper[0]["fast"] is True
    assert fake_whisper[0]["nbytes"] == ws_transcribe.BYTES_PER_SEC
    assert fake_whisper[1]["fast"] is False
    assert fake_whisper[1]["nbytes"] == 2 * ws_transcribe.BYTES_PER_SEC


def test_ws_short_audio_skips_whisper(fake_whisper) -> None:
    """Moins de 0,25 s : texte vide, Whisper n'est pas appele."""
    client = TestClient(_app())
    with client.websocket_connect("/ws/v1/transcribe") as ws:
        ws.receive_json()
        ws.send_bytes(_pcm(0.1))
        ws.send_text('{"op":"transcribe"}')
        msg = ws.receive_json()
        assert msg["type"] == "partial"
        assert msg["text"] == ""
    assert fake_whisper == []


def test_ws_reset_and_bad_json(fake_whisper) -> None:
    """reset vide le buffer ; un JSON casse renvoie error sans couper."""
    client = TestClient(_app())
    with client.websocket_connect("/ws/v1/transcribe?window_sec=4") as ws:
        ws.receive_json()
        ws.send_bytes(_pcm(0.5))
        ws.send_text('{"op":"reset"}')
        assert ws.receive_json()["type"] == "reset"
        ws.send_text("pas du json")
        err = ws.receive_json()
        assert err["type"] == "error"
        ws.send_text('{"op":"ping"}')
        assert ws.receive_json()["type"] == "pong"
        ws.send_text('{"op":"transcribe"}')
        empty = ws.receive_json()
        assert empty["text"] == ""
        assert empty["buffered"] == 0
    assert fake_whisper == []


def test_ws_rejects_bad_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans le bon token, la socket se ferme (4401)."""
    monkeypatch.setenv("STT_INTERNAL_TOKEN", "secret")
    client = TestClient(_app())
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/v1/transcribe") as ws:
            ws.receive_json()


def test_ws_accepts_token_query(fake_whisper, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le token en query ouvre la session."""
    monkeypatch.setenv("STT_INTERNAL_TOKEN", "secret")
    client = TestClient(_app())
    with client.websocket_connect("/ws/v1/transcribe?token=secret") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(_pcm(0.4))
        ws.send_text('{"op":"end"}')
        msg = ws.receive_json()
        assert msg["type"] == "final"
        assert msg["text"] == "bonjour madame"
    assert fake_whisper[0]["fast"] is False


def test_ws_header_token(fake_whisper, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le header X-STT-Token est accepte."""
    monkeypatch.setenv("STT_INTERNAL_TOKEN", "secret")
    client = TestClient(_app())
    with client.websocket_connect(
        "/ws/v1/transcribe",
        headers={"X-STT-Token": "secret"},
    ) as ws:
        assert ws.receive_json()["type"] == "ready"


def test_ws_engine_error_stays_open(fake_whisper, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si Whisper leve, on renvoie error et la socket reste ouverte."""

    def _boom(pcm: bytes, sample_rate: int = 16000, *, fast: bool = False) -> str:
        raise RuntimeError("modele KO")

    monkeypatch.setattr(ws_transcribe.stt_engine, "transcribe_pcm16", _boom)
    client = TestClient(_app())
    with client.websocket_connect("/ws/v1/transcribe") as ws:
        ws.receive_json()
        ws.send_bytes(_pcm(0.4))
        ws.send_text('{"op":"transcribe"}')
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "modele KO" in err["detail"]
        ws.send_text('{"op":"ping"}')
        assert ws.receive_json()["type"] == "pong"


def test_route_registered_on_stt_app() -> None:
    """Le service STT expose bien /ws/v1/transcribe et la feature health."""
    from backend.stt_service.app import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/ws/v1/transcribe" in paths
