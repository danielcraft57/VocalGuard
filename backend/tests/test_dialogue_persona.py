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


def test_ice_breaker_plus_leave_message_keeps_catalog():
    """oui bonjour + laisser un message : pas de repeat_hello, intent message."""
    from backend.voice.dialogue_persona import (
        is_ice_breaker_only,
        substance_after_ice_breaker,
        predict_text_for_intent,
    )

    text = "oui bonjour, j'aimerais laisser une message"
    assert not is_ice_breaker_only(text)
    assert "laisser" in substance_after_ice_breaker(text)
    assert "bonjour" not in predict_text_for_intent(text, ["salutation"]).lower()

    preds = [
        {"tag": "salutation", "score": 0.5},
        {"tag": "aide_menu", "score": 0.2},
        {"tag": "absent_laisser_message", "score": 0.3},
    ]
    out = resolve_dialogue_reply(
        user_text=text,
        predictions=preds,
        recent_tags=["salutation"],
        recent_replies=["Bonjour, assistante de monsieur Daniel."],
        recent_user_texts=[],
        catalog_responses=[
            "D'accord. Apres le bip, laissez votre message. Nous vous rappellerons."
        ],
    )
    assert out.get("persona_reason") is None
    assert out["tag"] == "absent_laisser_message"
    assert "bip" in out["reply"].lower() or "message" in out["reply"].lower()
    assert "deja salue" not in out["reply"].lower()


def test_ice_breaker_plus_ask_person_keeps_catalog():
    preds = [
        {"tag": "salutation", "score": 0.4},
        {"tag": "pour_personne", "score": 0.35},
        {"tag": "aide_menu", "score": 0.25},
    ]
    out = resolve_dialogue_reply(
        user_text="bonjour, mr daniel est là ?",
        predictions=preds,
        recent_tags=["salutation"],
        recent_replies=["Bonjour."],
        recent_user_texts=[],
        catalog_responses=[
            "Personne n'est disponible en direct. Laissez le nom de la personne visee."
        ],
    )
    assert out.get("persona_reason") is None
    assert out["tag"] in ("pour_personne", "parler_humain", "parler_direction", "absent_laisser_message")
    assert "deja salue" not in out["reply"].lower()


def test_contact_loic_and_presence_routing():
    """Contacter Loic / il est la ? ne doivent pas partir en rdv ou message direct."""
    preds = [
        {"tag": "prise_rdv", "score": 0.4},
        {"tag": "contacter_personne", "score": 0.3},
        {"tag": "parler_direction", "score": 0.2},
        {"tag": "aide_menu", "score": 0.1},
    ]
    out = resolve_dialogue_reply(
        user_text="bonjour, je cherche a contacter loic",
        predictions=preds,
        recent_tags=["salutation"],
        recent_replies=["Bonjour."],
        recent_user_texts=[],
        catalog_responses=[
            "Il n'est pas disponible en direct. Laissez votre nom, le motif et un numero."
        ],
    )
    assert out.get("persona_reason") is None
    assert out["tag"] == "contacter_personne"

    preds2 = [
        {"tag": "absent_laisser_message", "score": 0.45},
        {"tag": "presence_demande", "score": 0.3},
        {"tag": "aide_menu", "score": 0.25},
    ]
    out2 = resolve_dialogue_reply(
        user_text="il est là ?",
        predictions=preds2,
        recent_tags=["salutation", "contacter_personne"],
        recent_replies=["Bonjour.", "Il n'est pas dispo."],
        recent_user_texts=["bonjour, je cherche a contacter loic"],
        catalog_responses=[
            "Non, pas disponible pour l'instant. Vous pouvez laisser un message."
        ],
    )
    assert out2["tag"] == "presence_demande"
    assert "disponible" in out2["reply"].lower() or "message" in out2["reply"].lower()


def test_rappel_moi_not_sms():
    preds = [
        {"tag": "contact_sms", "score": 0.5},
        {"tag": "rappel_callback", "score": 0.3},
        {"tag": "prendre_coordonnees", "score": 0.2},
    ]
    out = resolve_dialogue_reply(
        user_text="5 rue du ponant ; rapelle moi ! Bisous",
        predictions=preds,
        recent_tags=["salutation", "contacter_personne"],
        recent_replies=[],
        recent_user_texts=[],
        catalog_responses=["OK pour un rappel. Laissez votre nom et un numero."],
    )
    assert out["tag"] == "rappel_callback"
    assert out.get("persona_reason") is None


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
