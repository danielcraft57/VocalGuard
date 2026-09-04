"""
Tests predict vectoriel (fallback cosine Python).
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base
from backend.services import intent_repository as intent_repo


@pytest.fixture()
def seeded_db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    root = Path(__file__).resolve().parents[2]
    catalog = intent_repo.load_seed_catalog(
        root / "data" / "intents" / "kb_seed" / "conversation_v1.json"
    )
    intent_repo.seed_intents_from_catalog(db, catalog, replace=True)
    yield db
    db.close()


def test_predict_rdv_top(seeded_db):
    """Phrase RDV → prise_rdv en tete ou proche."""
    preds = intent_repo.predict_intent_scores(
        seeded_db,
        "bonjour je voudrais prendre rendez-vous s il vous plait",
        top_k=5,
        use_pgvector=False,
    )
    assert preds
    tags = [p["tag"] for p in preds]
    assert "prise_rdv" in tags
    assert preds[0]["score"] > 0


def test_pattern_boost_message(seeded_db):
    """Boost lexical message."""
    boost = intent_repo.pattern_boost_scores(seeded_db, "je voudrais laisser un message")
    assert boost.get("absent_laisser_message", 0) > 0
