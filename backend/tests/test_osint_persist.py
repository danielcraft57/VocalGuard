"""Tests persistance OSINT normalisee (sans JSON)."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, PhoneNumberProfile, PhoneOsintSource
from backend.osint.persist import apply_osint_result_to_profile, source_codes_for_profile


def test_apply_osint_persists_scalars_and_sources() -> None:
    """Les flags / spam_type et les sources sont stockes en colonnes / table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    profile = PhoneNumberProfile(
        phone_number="0424284656",
        normalized_number="+33424284656",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    apply_osint_result_to_profile(
        db,
        profile,
        {
            "country": "FR",
            "city": "Lyon",
            "carrier": "Orange",
            "reputation": "low",
            "is_spam": True,
            "is_scam": False,
            "is_telemarketer": True,
            "is_commercial": True,
            "is_robocall": False,
            "spam_type": "Telemarketing",
            "spam_score": 7.0,
            "confidence": 0.8,
            "company_siren": "123456789",
            "sources": ["phoneinfoga", "tellows_html", "phoneinfoga"],
        },
    )
    db.commit()
    db.refresh(profile)

    assert profile.is_spam is True
    assert profile.is_telemarketer is True
    assert profile.is_robocall is False
    assert profile.spam_type == "Telemarketing"
    assert profile.spam_score == 7.0
    assert profile.confidence == 80
    assert profile.company_siren == "123456789"
    codes = source_codes_for_profile(profile)
    assert codes == ["phoneinfoga", "tellows_html"]
    assert db.query(PhoneOsintSource).filter_by(profile_id=profile.id).count() == 2
    db.close()


def test_apply_osint_rejects_dirty_spam_type() -> None:
    """Un spam_type contenant une URL n'est pas persiste."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    profile = PhoneNumberProfile(
        phone_number="0102030405",
        normalized_number="+33102030405",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        spam_type="image",
    )
    db.add(profile)
    db.commit()
    apply_osint_result_to_profile(
        db,
        profile,
        {"spam_type": "//tellows.de/search?number=1", "sources": []},
    )
    db.commit()
    db.refresh(profile)
    assert profile.spam_type is None
    db.close()


def test_apply_osint_rejects_image_spam_type() -> None:
    """Artefact HTML data-type=image ne doit pas rester en base."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    profile = PhoneNumberProfile(
        phone_number="0424284656",
        normalized_number="+33424284656",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        spam_type="image",
    )
    db.add(profile)
    db.commit()
    apply_osint_result_to_profile(
        db,
        profile,
        {"spam_type": "image", "reputation": "neutral", "sources": ["tellows_html"]},
    )
    db.commit()
    db.refresh(profile)
    assert profile.spam_type is None
    db.close()
