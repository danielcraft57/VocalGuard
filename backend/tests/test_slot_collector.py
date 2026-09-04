"""
Tests collecte de slots (coords / email / RDV).
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, CallLead
from backend.voice.slot_collector import (
    extract_slot_value,
    feed_slot_utterance,
    persist_call_lead,
    slots_for_action,
    start_slot_session,
)


def test_slots_for_actions():
    assert slots_for_action("collect_coords") == ["nom", "telephone", "email"]
    assert slots_for_action("collect_email") == ["email"]
    assert "creneau" in slots_for_action("collect_rdv_slot")


def test_extract_email_and_phone():
    assert extract_slot_value("email", "mon mail c'est loic@example.com merci") == "loic@example.com"
    phone = extract_slot_value("telephone", "rappelez-moi au 06 12 34 56 78")
    assert phone is not None
    assert "0612345678" in phone.replace(" ", "") or phone.endswith("5678")


def test_feed_and_persist(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leads.db'}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    session = start_slot_session("collect_coords", "prendre_coordonnees")
    assert session is not None
    assert feed_slot_utterance(session, "je m'appelle Dupont")
    assert feed_slot_utterance(session, "06 11 22 33 44")
    assert feed_slot_utterance(session, "dupont@test.fr")
    assert session.done
    lead = persist_call_lead(db, session, call_id=None, phone_number="+331")
    assert lead.name and "Dupont" in lead.name
    assert lead.email == "dupont@test.fr"
    assert db.query(CallLead).count() == 1
    db.close()
