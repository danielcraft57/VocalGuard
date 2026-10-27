"""Tests enrichissement noms prospect vs OSINT."""

from backend.services.prospect_phone_enrichment_service import compute_name_match_status


def test_name_match_exact() -> None:
    assert compute_name_match_status("Cafe du Centre", "Cafe du Centre", None) == "match"


def test_name_match_partial() -> None:
    assert compute_name_match_status("Restaurant Le Bistrot", "Le Bistrot Sarl") == "partial"


def test_name_match_mismatch() -> None:
    assert compute_name_match_status("Boulangerie X", "Garage Y") == "mismatch"
