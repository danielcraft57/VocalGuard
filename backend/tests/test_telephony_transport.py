"""
Tests transport telephonie (modem adapter + VoIP stub loopback).
"""

from __future__ import annotations

import asyncio

import pytest

from backend.core.telephony_transport import (
    DualTransport,
    ModemTransport,
    TelephonyBackend,
    VoipTransport,
    create_telephony_transport,
    parse_telephony_backend,
)


def test_parse_telephony_backend():
    assert parse_telephony_backend("modem") == TelephonyBackend.MODEM
    assert parse_telephony_backend("voip") == TelephonyBackend.VOIP
    assert parse_telephony_backend("SIP") == TelephonyBackend.VOIP
    assert parse_telephony_backend("dual") == TelephonyBackend.DUAL
    assert parse_telephony_backend(None) == TelephonyBackend.MODEM


@pytest.mark.asyncio
async def test_voip_stub_dial_echo_loopback():
    """Dial ouvre une session ; write_pcm revient en read_pcm (echo)."""
    voip = VoipTransport()
    assert await voip.start() is True
    ok, detail = await voip.dial("+33123456789")
    assert ok is True
    assert "loopback" in detail

    sample = bytes([0x01, 0x00, 0x02, 0x00] * 100)
    assert await voip.write_pcm(sample) is True
    echoed = await voip.read_pcm(len(sample))
    assert echoed == sample

    assert await voip.hangup() is True
    assert await voip.write_pcm(sample) is False
    await voip.stop()
    assert voip.is_initialized is False


@pytest.mark.asyncio
async def test_voip_simulate_incoming_triggers_callback():
    """simulate_incoming appelle on_incoming puis answer ouvre la session."""
    voip = VoipTransport()
    await voip.start()
    seen: list[tuple[str, str | None]] = []

    async def _on_incoming(number: str, name: str | None = None) -> None:
        seen.append((number, name))

    voip.on_incoming = _on_incoming
    assert await voip.simulate_incoming("0611223344", "Test") is True
    assert seen == [("0611223344", "Test")]
    assert await voip.answer() is True
    snap = voip.health_snapshot()
    assert snap["voip_session"]["direction"] == "in"
    assert snap["voip_session"]["phone_number"] == "0611223344"
    await voip.hangup()
    await voip.stop()


def test_create_transport_voip_without_modem():
    t = create_telephony_transport(TelephonyBackend.VOIP)
    assert isinstance(t, VoipTransport)


def test_create_transport_modem_requires_modem():
    with pytest.raises(ValueError):
        create_telephony_transport(TelephonyBackend.MODEM, modem=None)


def test_create_transport_dual_wraps_modem():
    class _FakeModem:
        is_initialized = True

        def health_snapshot(self):
            return {"modem_initialized": True}

    dual = create_telephony_transport(TelephonyBackend.DUAL, modem=_FakeModem())
    assert isinstance(dual, DualTransport)
    assert dual.name == "dual"
