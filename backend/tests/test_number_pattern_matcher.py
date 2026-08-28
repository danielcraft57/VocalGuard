"""Tests number_pattern_matcher."""

from backend.core.incoming_call_types import IncomingNumberPatternRule
from backend.core.number_pattern_matcher import match_pattern_rule, match_number_pattern_profile


def test_prefix_percent():
    rule = IncomingNumberPatternRule(pattern="+338%", action="blocked")
    assert match_pattern_rule("+33812345678", rule)
    assert not match_pattern_rule("+33123456789", rule)


def test_masked_p():
    rule = IncomingNumberPatternRule(pattern="P", action="blocked")
    assert match_pattern_rule("P", rule)
    assert match_pattern_rule("PRIVATE", rule)


def test_regex():
    rule = IncomingNumberPatternRule(pattern="^08", action="blocked")
    assert match_pattern_rule("0812345678", rule)


def test_whitelist_priority_via_policy():
    from backend.core.config import Config
    from backend.core.incoming_call_policy import IncomingCallPolicy

    config = Config()
    policy = IncomingCallPolicy(config)
    policy.settings.number_patterns.enabled = True
    decision = policy.resolve_sync(caller_id="+33899999999", is_whitelisted=True)
    assert decision.profile == "permitted"
