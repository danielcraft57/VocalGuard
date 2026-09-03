"""Tests du moteur worker OSINT (normalisation, mapping ProspectLab)."""

from backend.osint_worker.engine import _digits_only, _map_prospectlab_entreprise


def test_digits_only_local_fr() -> None:
    """Un 06 local devient 336... pour PhoneInfoga."""
    assert _digits_only("06 12 34 56 78") == "33612345678"


def test_digits_only_e164() -> None:
    """Le + est retire, les chiffres restent."""
    assert _digits_only("+33612345678") == "33612345678"


def test_map_prospectlab_entreprise() -> None:
    """La fiche ProspectLab remplit company_* et le site web."""
    mapped = _map_prospectlab_entreprise(
        {
            "id": 42,
            "nom": "Atelier Demo",
            "siren": "123456789",
            "siret": "12345678900011",
            "ville": "Lyon",
            "code_postal": "69001",
            "adresse": "1 rue Test",
            "site_web": "https://exemple.fr",
            "naf": "62.01Z",
        }
    )
    assert mapped["is_company"] is True
    assert mapped["company_name"] == "Atelier Demo"
    assert mapped["company_siren"] == "123456789"
    assert mapped["city"] == "Lyon"
    assert mapped["social_media"]["website"] == "https://exemple.fr"
    assert "prospectlab" in mapped["sources"]
