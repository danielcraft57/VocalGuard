"""
Smoke events belief conversation (sans modem).
"""

import asyncio
from datetime import datetime

import pytest

from backend.core.events import Event, EventType, event_bus
from backend.voice.intent_belief import BeliefConfig, IntentBeliefAccumulator


@pytest.mark.asyncio
async def test_belief_events_payload_shape():
    """Chunks → belief → commit publient un payload exploitable par la modal."""
    received = []

    async def handler(event: Event):
        received.append(event)

    event_bus.subscribe(EventType.CALL_INTENT_BELIEF, handler)
    event_bus.subscribe(EventType.CALL_INTENT_COMMIT, handler)
    try:
        acc = IntentBeliefAccumulator(
            BeliefConfig(alpha=1.0, min_chunks=1, min_speech_ms=0, commit_threshold=0.6, commit_margin=0.05)
        )
        acc.update({"prise_rdv": 0.8, "salutation": 0.1}, speech_ms=700)
        await event_bus.publish(
            Event(
                event_type=EventType.CALL_INTENT_BELIEF,
                timestamp=datetime.utcnow(),
                data=acc.as_event_payload(call_id=42),
                source="test",
            )
        )
        tag = acc.try_commit()
        assert tag == "prise_rdv"
        await event_bus.publish(
            Event(
                event_type=EventType.CALL_INTENT_COMMIT,
                timestamp=datetime.utcnow(),
                data={"call_id": 42, "tag": tag, "text": "prendre rdv"},
                source="test",
            )
        )
        await asyncio.sleep(0.05)
        types = [e.event_type for e in received]
        assert EventType.CALL_INTENT_BELIEF in types
        assert EventType.CALL_INTENT_COMMIT in types
        belief_ev = next(e for e in received if e.event_type == EventType.CALL_INTENT_BELIEF)
        assert belief_ev.data["call_id"] == 42
        assert "top" in belief_ev.data
    finally:
        event_bus.unsubscribe(EventType.CALL_INTENT_BELIEF, handler)
        event_bus.unsubscribe(EventType.CALL_INTENT_COMMIT, handler)
