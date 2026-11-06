"""Fixtures pytest Prospector."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from desktop.prospector.db.models import ProspectorBase
from desktop.prospector.db.session import get_engine


@pytest.fixture()
def prospector_db(monkeypatch):
    """SQLite memoire + schema."""
    monkeypatch.setenv("VG_PROSPECTOR_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    get_engine.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    ProspectorBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        get_engine.cache_clear()
