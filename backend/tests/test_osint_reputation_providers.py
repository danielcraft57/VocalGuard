"""Tests des helpers reputation OSINT worker."""

from backend.osint_worker.reputation import (
    _category_flags,
    _digits_e164,
    _parse_tellows_html,
    _spamcalls_page_matches,
    _tellows_result,
    is_plausible_spam_type,
    merge_reputation,
    providers_status,
)


def test_digits_e164_local_fr() -> None:
    assert _digits_e164("06 12 34 56 78") == "+33612345678"


def test_category_flags_telemarketing() -> None:
    flags = _category_flags("Telemarketing")
    assert flags["is_telemarketer"] is True
    assert flags["is_commercial"] is True
    assert flags["is_spam"] is True


def test_category_flags_scam() -> None:
    flags = _category_flags("SCAM / arnaque")
    assert flags["is_scam"] is True
    assert flags["is_spam"] is True


def test_category_flags_rejects_image_junk() -> None:
    """data-type=image (pub Google) ne doit pas produire de flags spam."""
    flags = _category_flags("image")
    assert flags["is_spam"] is False
    assert flags["is_scam"] is False


def test_is_plausible_spam_type() -> None:
    assert is_plausible_spam_type("Telemarketing") is True
    assert is_plausible_spam_type("SCAM / arnaque") is True
    assert is_plausible_spam_type("image") is False
    assert is_plausible_spam_type("//tellows.de/x") is False
    assert is_plausible_spam_type("/images/score/s5.jpg") is False


def test_tellows_high_score_is_spam() -> None:
    res = _tellows_result(8, ["Scam"], None, "33123456789", "html")
    assert res["is_spam"] is True
    assert res["is_scam"] is True
    assert res["reputation"] == "low"


def test_tellows_mid_score_neutral() -> None:
    res = _tellows_result(5, [], None, "33123456789", "html")
    assert res["is_spam"] is False
    assert res["reputation"] == "neutral"


def test_tellows_low_score_is_safe() -> None:
    res = _tellows_result(1, [], "Orange", "33123456789", "api")
    assert res["reputation"] == "high"
    assert res["is_spam"] is False
    assert res["name"] == "Orange"


def test_tellows_html_ignores_data_type_image() -> None:
    """Le HTML Tellows actuel utilise s5.jpg + data-type=image (ads)."""
    html = """
    <img class="scoreimage" src="/images/score/s5.jpg"
         alt="tellows Note pour  +3333424284656 : Score 5" />
    <div data-theme="light" data-type="image"></div>
    <span class="callertype">Telemarketing</span>
    """
    res = _parse_tellows_html(html, "33424284656", "https://www.tellows.fr/num/33424284656")
    assert res.get("spam_score") == 5.0
    assert res.get("spam_type") == "Telemarketing"
    assert res.get("is_telemarketer") is True
    assert res.get("reputation") == "low"


def test_tellows_html_score_only_no_junk_type() -> None:
    html = """
    <img class="scoreimage" src="/images/score/s3.jpg" alt="Score 3" />
    <div data-type="image"></div>
    """
    res = _parse_tellows_html(html, "33123456789", "https://www.tellows.fr/num/33123456789")
    assert res.get("spam_score") == 3.0
    assert res.get("spam_type") is None
    assert res.get("reputation") == "high"


def test_spamcalls_page_match() -> None:
    html = "<html><head><title>+33424284656 Who owns</title></head><body><h1>+33424284656</h1></body></html>"
    assert _spamcalls_page_matches(html, "https://spamcalls.net/en/num/33424284656", "33424284656")
    bad_html = "<html><head><title>+33424285211</title></head><body><h1>+33424285211</h1></body></html>"
    assert not _spamcalls_page_matches(
        bad_html, "https://spamcalls.net/en/num/33424285211", "33424284656"
    )


def test_merge_reputation_low_wins() -> None:
    base = {"sources": ["a"], "reputation": "high", "is_spam": False, "confidence": 0.5}
    new = {"sources": ["b"], "reputation": "low", "is_spam": True, "confidence": 0.9}
    out = merge_reputation(base, new)
    assert out["reputation"] == "low"
    assert out["is_spam"] is True
    assert "b" in out["sources"]
    assert out["confidence"] == 0.9


def test_merge_reputation_rejects_junk_spam_type() -> None:
    base = {"sources": [], "reputation": None}
    out = merge_reputation(
        base, {"sources": ["tellows_html"], "spam_type": "image", "reputation": "neutral"}
    )
    assert out.get("spam_type") is None
    assert "tellows_html" in out["sources"]


def test_providers_status_shape() -> None:
    status = providers_status()
    assert "tellows" in status
    assert "spamcalls" in status
    assert "huhu" in status
    assert status["tellows"]["enabled"] is True
