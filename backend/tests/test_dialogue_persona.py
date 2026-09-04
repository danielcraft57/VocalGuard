"""
Tests persona de dialogue (contexte, repetitions, humeur).
"""

from backend.voice.dialogue_persona import (
    persona_override,
    reshape_predictions,
    resolve_dialogue_reply,
    compute_mood,
)


def test_repeat_bonjour_triggers_persona():
    preds = [
        {"tag": "salutation", "score": 0.8},
        {"tag": "aide_menu", "score": 0.2},
    ]
    out = resolve_dialogue_reply(
        user_text="bonjour",
        predictions=preds,
        recent_tags=["salutation"],
        recent_replies=["Bonjour, vous etes bien sur la messagerie."],
        recent_user_texts=[],
        catalog_responses=["Bonjour encore une fois."],
    )
    assert out["persona_reason"] == "repeat_hello"
    assert "perroquet" in out["reply"].lower() or "salue" in out["reply"].lower() or "ensuite" in out["reply"].lower()
    assert out["reply"] != "Bonjour encore une fois."


def test_reshape_demotes_salutation_after_seen():
    preds = [
        {"tag": "salutation", "score": 0.7},
        {"tag": "aide_menu", "score": 0.3},
    ]
    out = reshape_predictions(
        preds, recent_tags=["salutation"], user_text="bonjour"
    )
    assert out[0]["tag"] == "aide_menu"


def test_mood_gets_ironic_on_heavy_repeat():
    mood = compute_mood(
        recent_tags=["salutation", "salutation"],
        recent_user_texts=["bonjour", "bonjour"],
        user_text="bonjour",
        predicted_tag="salutation",
    )
    assert mood.patience < 0.5
    assert mood.tone in ("annoyed", "ironic", "firm")


def test_persona_override_repeat_hello():
    from backend.voice.dialogue_persona import DialogueMood

    mood = DialogueMood(patience=0.3, tone="annoyed", user_repeat=2, tag_streak=2)
    ov = persona_override(
        user_text="bonjour",
        predicted_tag="salutation",
        mood=mood,
        recent_tags=["salutation"],
        recent_replies=[],
    )
    assert ov is not None
    assert ov[1] == "repeat_hello"


def test_insult_triggers_persona_and_escalates():
    preds = [{"tag": "aide_menu", "score": 0.6}, {"tag": "salutation", "score": 0.4}]
    first = resolve_dialogue_reply(
        user_text="espèce de connard",
        predictions=preds,
        recent_tags=["salutation"],
        recent_replies=[],
        recent_user_texts=[],
        catalog_responses=["Menu."],
    )
    assert first["persona_reason"] == "insult"
    assert first["tag"] == "insulte"
    assert "courtois" in first["reply"].lower() or "injure" in first["reply"].lower() or "insult" in first["reply"].lower() or "ton" in first["reply"].lower()

    third = resolve_dialogue_reply(
        user_text="ta gueule abruti",
        predictions=preds,
        recent_tags=["salutation", "insulte", "insulte"],
        recent_replies=[first["reply"], "x"],
        recent_user_texts=["connard", "idiot"],
        catalog_responses=["Menu."],
    )
    assert third["persona_reason"] == "insult"
    assert third.get("action") == "hangup_soft"
