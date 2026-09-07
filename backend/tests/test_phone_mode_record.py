"""Tests greffe silencieuse mode telephone (sans modem physique)."""

from __future__ import annotations

from unittest.mock import PropertyMock

import pytest

from backend.core.modem_handler import ModemHandler, _TAD_OFF_HOOK, _VOICE_MODE


@pytest.mark.asyncio
async def test_join_line_for_listen_vls_after_ath_fail(monkeypatch):
    """Si ATH1 echoue, VLS=1 peut encore greffer pour l'ecoute."""
    modem = ModemHandler.__new__(ModemHandler)
    modem._incoming_line_seized = False
    modem._incoming_seize_ok = False
    modem._voice_line_ready = False

    calls: list[str] = []

    async def fake_send(cmd: str, timeout: float = 5.0, **kwargs):
        calls.append(cmd)
        if cmd == "ATH1":
            return b"NO CARRIER\r\n"
        if cmd == _VOICE_MODE:
            return b"OK\r\n"
        if cmd == _TAD_OFF_HOOK:
            return b"OK\r\n"
        return b"OK\r\n"

    async def fake_prepare():
        modem._voice_line_ready = True

    monkeypatch.setattr(
        type(modem),
        "supports_voice_serial",
        PropertyMock(return_value=True),
    )
    modem.send_command_full = fake_send  # type: ignore[method-assign]
    modem.prepare_voice_line_after_seize = fake_prepare  # type: ignore[method-assign]

    ok = await modem.join_line_for_listen()
    assert ok is True
    assert "ATH1" in calls
    assert _VOICE_MODE in calls
    assert _TAD_OFF_HOOK in calls
    assert modem._incoming_seize_ok is True


@pytest.mark.asyncio
async def test_join_line_for_listen_fails_when_vls_ko(monkeypatch):
    modem = ModemHandler.__new__(ModemHandler)
    modem._incoming_line_seized = False
    modem._incoming_seize_ok = False

    async def fake_send(cmd: str, timeout: float = 5.0, **kwargs):
        if cmd == "ATH1":
            return b"NO CARRIER\r\n"
        if cmd == _VOICE_MODE:
            return b"OK\r\n"
        if cmd == _TAD_OFF_HOOK:
            return b"ERROR\r\n"
        return b"ERROR\r\n"

    monkeypatch.setattr(
        type(modem),
        "supports_voice_serial",
        PropertyMock(return_value=True),
    )
    modem.send_command_full = fake_send  # type: ignore[method-assign]

    assert await modem.join_line_for_listen() is False
