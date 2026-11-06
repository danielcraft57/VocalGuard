"""Tests migrations SQLite Prospector."""

from __future__ import annotations

from sqlalchemy import inspect

from desktop.prospector.db.models import PlGroupe


def test_migrations_create_tables(prospector_db):
    """Verifie les tables principales."""
    insp = inspect(prospector_db.bind)
    names = set(insp.get_table_names())
    assert "pl_groupe" in names
    assert "queue_item" in names
    assert "call_session" in names


def test_insert_groupe(prospector_db):
    """Insert minimal pl_groupe."""
    g = PlGroupe(prospectlab_id=42, nom="Test")
    prospector_db.add(g)
    prospector_db.commit()
    assert g.id is not None
