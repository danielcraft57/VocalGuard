"""Construction de la reponse OSINT attachee aux appels."""

from types import SimpleNamespace

from backend.api.routes.calls import _profile_to_osint_response


def test_profile_to_osint_includes_company() -> None:
    """Le nom d'entreprise du profil est expose dans l'OSINT des appels."""
    profile = SimpleNamespace(
        reputation="neutral",
        region="Lorraine",
        city="Nancy",
        operator="Orange",
        confidence=40,
        is_spam=False,
        is_scam=False,
        is_commercial=False,
        is_telemarketer=False,
        is_company=True,
        name="INGEDUS.COM Nancy",
        company_name="INGEDUS.COM Nancy",
        raw_data={"sources": ["phoneinfoga", "prospectlab"]},
    )
    resp = _profile_to_osint_response(profile, "+33383123456")
    assert resp.company_name == "INGEDUS.COM Nancy"
    assert resp.is_company is True
    assert "prospectlab" in resp.sources
    assert resp.city == "Nancy"
