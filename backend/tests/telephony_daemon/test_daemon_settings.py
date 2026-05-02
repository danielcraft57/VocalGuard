"""Configuration du processus daemon : pas de proxification recursive."""

from __future__ import annotations

import pytest


def test_load_daemon_config_disables_outgoing_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_TELEPHONY_DAEMON", "1")
    from backend.telephony_daemon.settings import load_daemon_config

    cfg = load_daemon_config()
    assert cfg.use_telephony_daemon is False
