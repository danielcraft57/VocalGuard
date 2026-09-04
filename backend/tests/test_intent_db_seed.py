"""
Tests seed intents → tables normalisees (SQLite).
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, Intent, IntentEmbedding, IntentPattern, IntentResponse
from backend.services import intent_repository as intent_repo


@pytest.fixture()
def db_session(tmp_path: Path):
    """Session SQLite isolee avec schema intents."""
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_seed_catalog_normalized(db_session, tmp_path: Path):
    """Import seed → intents / patterns / responses / embeddings sans blob JSON metier."""
    root = Path(__file__).resolve().parents[2]
    catalog_path = root / "data" / "intents" / "kb_seed" / "conversation_v1.json"
    assert catalog_path.is_file()
    catalog = intent_repo.load_seed_catalog(catalog_path)
    n = intent_repo.seed_intents_from_catalog(db_session, catalog, replace=True)
    assert n >= 10
    tags = {i.tag for i in db_session.query(Intent).all()}
    assert "absent_laisser_message" in tags
    assert "prise_rdv" in tags
    assert "prendre_coordonnees" in tags
    assert db_session.query(IntentPattern).count() > 0
    assert db_session.query(IntentResponse).count() > 0
    emb = db_session.query(IntentEmbedding).first()
    assert emb is not None
    assert isinstance(emb.embedding_json, list)
    assert len(emb.embedding_json) == 384


def test_ensure_seeded_idempotent(db_session, tmp_path: Path):
    """Deuxieme ensure ne re-seed pas."""
    root = Path(__file__).resolve().parents[2]
    # Copie relative via base_path
    n1 = intent_repo.ensure_seeded(db_session, root)
    n2 = intent_repo.ensure_seeded(db_session, root)
    assert n1 > 0
    assert n2 == 0
