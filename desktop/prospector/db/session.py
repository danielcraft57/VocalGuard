"""
Engine et sessions SQLAlchemy Prospector.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from desktop.prospector.settings import database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    Engine SQLite avec FK activees.

    @returns Engine SQLAlchemy.
    """
    url = database_url()
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def session_scope() -> Session:
    """
    Nouvelle session (fermeture manuelle).

    @returns Session SQLAlchemy.
    """
    return SessionLocal()
