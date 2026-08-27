"""Tests unitaires incoming_call_settings et policy."""

from backend.core.config import Config
from backend.core.incoming_call_policy import (
    IncomingCallPolicy,
    classify_profile_sync,
    match_number_pattern_profile,
)
from backend.core.incoming_call_settings import (
    load_incoming_call_settings,
    patch_incoming_call_settings,
    resolve_profile_decision,
)
from backend.core.incoming_call_types import IncomingNumberPatternRule, IncomingNumberPatternsConfig


def test_classify_profile_sync():
    assert classify_profile_sync(is_whitelisted=True) == "permitted"
    assert classify_profile_sync(is_blocked=True) == "blocked"
    assert classify_profile_sync() == "screened"


def test_resolve_profile_decision_voicemail_screened():
    config = Config()
    settings = load_incoming_call_settings(config)
    settings.active_preset = "voicemail"
    resolved = resolve_profile_decision(settings, "screened")
    assert resolved.rings_before_answer == 0
    assert "answer" in resolved.actions
    assert resolved.seize_on_ring is True


def test_patch_whitelist_ring_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    config = Config()
    config.base_path = tmp_path
    patched = patch_incoming_call_settings(config, {"whitelist_ring_only": True})
    assert patched.whitelist_ring_only is True
    assert config.whitelist_ring_only is True
    reloaded = load_incoming_call_settings(config)
    assert reloaded.whitelist_ring_only is True


def test_policy_reload():
    config = Config()
    policy = IncomingCallPolicy(config)
    decision = policy.resolve_sync(is_blocked=True)
    assert decision.profile == "blocked"
    assert decision.should_answer is True


def test_whitelist_ring_only_ignore():
    config = Config()
    config.whitelist_ring_only = True
    policy = IncomingCallPolicy(config)
    decision = policy.resolve_sync(caller_id="+33123456789", is_whitelisted=True)
    assert decision.profile == "permitted"
    assert decision.should_ignore is True
    assert decision.should_answer is False


def test_number_pattern_masked():
    config = Config()
    settings = load_incoming_call_settings(config)
    settings.number_patterns = IncomingNumberPatternsConfig(
        enabled=True,
        rules=[IncomingNumberPatternRule(pattern="P", action="blocked", reason="masque")],
    )
    assert match_number_pattern_profile("P", settings) == "blocked"
