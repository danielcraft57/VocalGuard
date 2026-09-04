"""
Tests selection de reponse anti-repetition.
"""

from backend.voice.response_picker import (
    apply_recent_tag_penalty,
    same_tag_streak,
    select_response,
    variant_wav_basename,
)


def test_select_prefers_fresh_variant():
    replies = ["A", "B", "C"]
    text, idx = select_response(replies, recent_replies=["A"], same_tag_streak=0)
    assert text == "B"
    assert idx == 1


def test_select_bridge_on_streak_when_exhausted():
    replies = ["Toujours la meme"]
    text, idx = select_response(
        replies,
        recent_replies=["Toujours la meme"],
        same_tag_streak=1,
    )
    assert text != "Toujours la meme"
    assert idx == -1


def test_recent_tag_penalty_reranks():
    preds = [
        {"tag": "prise_rdv", "score": 0.55},
        {"tag": "tarifs_devis", "score": 0.45},
    ]
    out = apply_recent_tag_penalty(preds, ["prise_rdv"])
    assert out[0]["tag"] == "tarifs_devis"


def test_streak_and_basename():
    assert same_tag_streak("a", ["b", "a", "a"]) == 2
    assert variant_wav_basename("prise_rdv", 0) == "kb_prise_rdv"
    assert variant_wav_basename("prise_rdv", 2) == "kb_prise_rdv_r2"
