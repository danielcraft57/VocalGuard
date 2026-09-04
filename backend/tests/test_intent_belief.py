"""
Tests accumulateur de croyance intents.
"""

from backend.voice.intent_belief import BeliefConfig, IntentBeliefAccumulator


def test_ema_fusion_and_renorm():
    """Fusion EMA puis somme ~1."""
    acc = IntentBeliefAccumulator(BeliefConfig(alpha=0.5, min_chunks=1, min_speech_ms=0))
    b = acc.update({"a": 1.0, "b": 0.0}, speech_ms=100)
    assert abs(sum(b.values()) - 1.0) < 1e-6
    # Deuxieme update fort sur b : b doit monter franchement
    b2 = acc.update({"a": 0.0, "b": 1.0}, speech_ms=100)
    b3 = acc.update({"a": 0.0, "b": 1.0}, speech_ms=100)
    assert b3["b"] > b3["a"]
    assert b3["b"] > b2["a"]


def test_commit_requires_threshold_margin_and_min_duration():
    """Pas de commit trop tot sur un seul chunk court."""
    acc = IntentBeliefAccumulator(
        BeliefConfig(
            alpha=1.0,
            commit_threshold=0.7,
            commit_margin=0.15,
            min_chunks=2,
            min_speech_ms=600,
        )
    )
    acc.update({"prise_rdv": 0.9, "salutation": 0.1}, speech_ms=200)
    assert acc.try_commit() is None
    acc.update({"prise_rdv": 0.85, "salutation": 0.1}, speech_ms=500)
    assert acc.try_commit() == "prise_rdv"


def test_force_fallback_incompris():
    """Fin de tour sous seuil bas → incompris."""
    acc = IntentBeliefAccumulator(BeliefConfig(low_threshold=0.35, fallback_tag="incompris"))
    # Scores bruts bas : apres renorm le max est 1.0 — on force via belief manuelle
    acc.state.belief = {"x": 0.2, "y": 0.1}
    acc.state.chunks = 1
    assert acc.try_commit(force=True) == "incompris"


def test_reset_clears_state():
    """Reset pour le tour suivant."""
    acc = IntentBeliefAccumulator(BeliefConfig(alpha=1.0, min_chunks=1, min_speech_ms=0, commit_threshold=0.5, commit_margin=0.0))
    acc.update({"fin": 0.9}, speech_ms=800)
    assert acc.try_commit() == "fin"
    acc.reset()
    assert acc.state.committed_tag is None
    assert acc.state.chunks == 0
