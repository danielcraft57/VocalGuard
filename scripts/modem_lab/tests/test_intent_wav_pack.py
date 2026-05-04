"""Tests extracteurs de placeholders sur JSON intents."""

from pathlib import Path

import pytest

import sys

_MODEM_LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_MODEM_LAB))

from labaudio.intent_wav_pack import collect_placeholder_keys_from_intent_json


def test_collect_keys_prospection_flow() -> None:
    root = _MODEM_LAB.parent.parent
    p = root / "data" / "intents_prospection_flow.json"
    if not p.is_file():
        pytest.skip("data/intents_prospection_flow.json absent")
    keys = collect_placeholder_keys_from_intent_json(p)
    assert "agent_name" in keys
    assert "company_name" in keys
