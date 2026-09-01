"""Tests unitaires logique DNS IONOS (sans appel reseau)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ionos_dns_lib import (
    build_a_record_payload,
    load_ionos_config_from_env,
    pick_existing_a_record,
    should_update_record,
    IonosDnsConfig,
)


def test_load_ionos_config_from_prefix_secret() -> None:
    cfg = load_ionos_config_from_env(
        {"IONOS_API_PREFIX": "abc", "IONOS_API_SECRET": "xyz", "VOCALGUARD_DNS_TARGET": "192.168.1.12"}
    )
    assert cfg.api_key == "abc.xyz"
    assert cfg.record_name == "vocalguard.danielcraft.fr"


def test_load_ionos_config_missing_key_raises() -> None:
    with pytest.raises(ValueError):
        load_ionos_config_from_env({})


def test_build_a_record_payload() -> None:
    cfg = IonosDnsConfig(api_key="k", target_ip="10.0.0.5")
    payload = build_a_record_payload(cfg)
    assert payload["type"] == "A"
    assert payload["content"] == "10.0.0.5"
    assert payload["name"] == "vocalguard"


def test_pick_existing_a_record() -> None:
    records = [
        {"id": "1", "name": "www", "type": "A", "content": "1.2.3.4"},
        {"id": "2", "name": "vocalguard", "type": "A", "content": "10.0.0.1"},
    ]
    found = pick_existing_a_record(records, "vocalguard")
    assert found is not None
    assert found["id"] == "2"


def test_should_update_record_when_ip_differs() -> None:
    assert should_update_record({"content": "1.1.1.1"}, "2.2.2.2") is True
    assert should_update_record({"content": "1.1.1.1"}, "1.1.1.1") is False
