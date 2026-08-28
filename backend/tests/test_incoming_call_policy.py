"""Tests format resume decision policy."""

from backend.core.config import Config
from backend.core.incoming_call_policy import IncomingCallPolicy
from backend.core.incoming_call_types import CallDecision


def test_remember_decision_summary_format():
    policy = IncomingCallPolicy(Config())
    decision = CallDecision(
        profile="screened",
        actions=["answer"],
        rings_before_answer=0,
        seize_on_ring=True,
        require_cid_before_action=False,
        source="preset:voicemail",
        should_ignore=False,
        should_answer=True,
    )
    policy.remember_decision(decision)
    summary = policy.last_decision_summary
    assert summary is not None
    assert summary.startswith("screened | preset:voicemail |")
    assert "rings=0" in summary
    assert "ignore=False" in summary
