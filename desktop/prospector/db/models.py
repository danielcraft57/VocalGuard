"""
Modeles SQLAlchemy Prospector (SQLite locale).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ProspectorBase(DeclarativeBase):
    """Base declarative Prospector."""


class PlImportBatch(ProspectorBase):
    """Trace d'un import ProspectLab."""

    __tablename__ = "pl_import_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="groupe")
    prospectlab_groupe_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    filters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)


class PlGroupe(ProspectorBase):
    """Cache groupe ProspectLab."""

    __tablename__ = "pl_groupe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospectlab_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    couleur: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    entreprises_count: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    memberships: Mapped[list["PlEntrepriseGroupe"]] = relationship(back_populates="groupe")


class PlEntreprise(ProspectorBase):
    """Cache entreprise ProspectLab."""

    __tablename__ = "pl_entreprise"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prospectlab_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(512), default="")
    secteur: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    statut_pl: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ville: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    code_postal: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    local_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    phones: Mapped[list["PlPhone"]] = relationship(back_populates="entreprise")
    group_links: Mapped[list["PlEntrepriseGroupe"]] = relationship(back_populates="entreprise")
    queue_items: Mapped[list["QueueItem"]] = relationship(back_populates="entreprise")


class PlPhone(ProspectorBase):
    """Telephone cache."""

    __tablename__ = "pl_phone"
    __table_args__ = (UniqueConstraint("entreprise_id", "phone_digits", name="uq_pl_phone_ent_digits"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entreprise_id: Mapped[int] = mapped_column(ForeignKey("pl_entreprise.id"), index=True)
    phone_raw: Mapped[str] = mapped_column(String(64), default="")
    phone_digits: Mapped[str] = mapped_column(String(32), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    entreprise: Mapped["PlEntreprise"] = relationship(back_populates="phones")


class PlEntrepriseGroupe(ProspectorBase):
    """Appartenance entreprise / groupe."""

    __tablename__ = "pl_entreprise_groupe"
    __table_args__ = (UniqueConstraint("entreprise_id", "groupe_id", name="uq_ent_groupe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entreprise_id: Mapped[int] = mapped_column(ForeignKey("pl_entreprise.id"), index=True)
    groupe_id: Mapped[int] = mapped_column(ForeignKey("pl_groupe.id"), index=True)

    entreprise: Mapped["PlEntreprise"] = relationship(back_populates="group_links")
    groupe: Mapped["PlGroupe"] = relationship(back_populates="memberships")


class QueueItem(ProspectorBase):
    """File d'appels sortants."""

    __tablename__ = "queue_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entreprise_id: Mapped[int] = mapped_column(ForeignKey("pl_entreprise.id"), index=True)
    import_batch_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pl_import_batch.id"), nullable=True)
    source_groupe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pl_groupe.id"), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    local_status: Mapped[str] = mapped_column(String(32), default="todo", index=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    entreprise: Mapped["PlEntreprise"] = relationship(back_populates="queue_items")
    source_groupe: Mapped[Optional["PlGroupe"]] = relationship()


class CallSession(ProspectorBase):
    """Journal session appel."""

    __tablename__ = "call_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(String(8), default="out")
    phone_digits: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    entreprise_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pl_entreprise.id"), nullable=True)
    queue_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("queue_item.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wav_session_dir: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    prospectlab_patch_pending: Mapped[bool] = mapped_column(Boolean, default=False)

    transcript_lines: Mapped[list["CallTranscriptLine"]] = relationship(back_populates="session")


class CallTranscriptLine(ProspectorBase):
    """Ligne transcription STT."""

    __tablename__ = "call_transcript_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_session_id: Mapped[int] = mapped_column(ForeignKey("call_session.id"), index=True)
    speaker: Mapped[str] = mapped_column(String(16), default="remote")
    text: Mapped[str] = mapped_column(Text, default="")
    is_final: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["CallSession"] = relationship(back_populates="transcript_lines")


class IncomingRingEvent(ProspectorBase):
    """Evenement sonnerie entrante."""

    __tablename__ = "incoming_ring_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rang_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    caller_id_raw: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    caller_id_digits: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    matched_entreprise_id: Mapped[Optional[int]] = mapped_column(ForeignKey("pl_entreprise.id"), nullable=True)
    user_action: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    call_session_id: Mapped[Optional[int]] = mapped_column(ForeignKey("call_session.id"), nullable=True)


class SyncOutbox(ProspectorBase):
    """File sync PATCH ProspectLab."""

    __tablename__ = "sync_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    method: Mapped[str] = mapped_column(String(8), default="PATCH")
    path: Mapped[str] = mapped_column(String(512))
    body_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AppSetting(ProspectorBase):
    """Cle / valeur preferences."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
