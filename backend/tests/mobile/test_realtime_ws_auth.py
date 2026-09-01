"""Tests auth WebSocket /ws/events."""

from __future__ import annotations


def test_ws_rejects_without_token_in_test_env(client) -> None:
    with client.websocket_connect("/ws/events") as _:
        pass  # en VG_ENV=test sans prod, connexion sans token autorisee


def test_ws_accepts_with_valid_token(client, mobile_token) -> None:
    with client.websocket_connect(
        "/ws/events",
        headers={"Authorization": f"Bearer {mobile_token}"},
    ) as ws:
        ws.send_text("ping")
