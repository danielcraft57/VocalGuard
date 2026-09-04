"""
Modèles de base de données SQLAlchemy
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Date,
    Boolean,
    Text,
    ForeignKey,
    Float,
    Table,
    Time,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import JSON as SA_JSON

# JSONB sur Postgres, JSON portable ailleurs (tests SQLite).
JsonbCompat = SA_JSON().with_variant(JSONB(), "postgresql")

Base = declarative_base()

entreprise_category_links = Table(
    "entreprise_category_links",
    Base.metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("entreprise_categories.id", ondelete="CASCADE"), primary_key=True),
)

entreprise_email_links = Table(
    "entreprise_email_links",
    Base.metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), primary_key=True),
    Column("email_id", Integer, ForeignKey("entreprise_emails.id", ondelete="CASCADE"), primary_key=True),
)


class Caller(Base):
    """Modele pour les appelants (pas de JSON metier)."""

    __tablename__ = "callers"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=False, index=True)
    is_whitelisted = Column(Boolean, default=False, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    calls = relationship("Call", back_populates="caller")


class FrenchPhonePrefix(Base):
    """Modele pour les prefixes de numeros francais"""

    __tablename__ = "french_phone_prefixes"

    id = Column(Integer, primary_key=True, index=True)
    prefix = Column(String(10), unique=True, index=True, nullable=False)
    city = Column(String(255), nullable=True)
    region = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    postal_code = Column(String(10), nullable=True)
    operator = Column(String(100), nullable=True)
    operator_type = Column(String(50), nullable=True)
    line_type = Column(String(20), nullable=True)
    latitude = Column(String(20), nullable=True)
    longitude = Column(String(20), nullable=True)
    population = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Call(Base):
    """Modele pour les appels (colonnes a plat, cues SRT en JSONB)."""

    __tablename__ = "calls"
    __table_args__ = (
        Index("ix_calls_call_time", "call_time"),
        Index("ix_calls_status", "status"),
        Index("ix_calls_phone_number", "phone_number"),
        Index("ix_calls_status_call_time", "status", "call_time"),
    )

    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("callers.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(20), nullable=True)
    caller_name = Column(String(255), nullable=True)

    call_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    answer_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    status = Column(String(50), default="ringing", nullable=False)
    duration = Column(Integer, nullable=True)

    transcription = Column(Text, nullable=True)
    audio_file = Column(String(500), nullable=True)

    # Ancien extra_data JSON -> colonnes
    incoming_profile = Column(String(32), nullable=True)
    incoming_policy_source = Column(String(128), nullable=True)
    incoming_rings = Column(Integer, nullable=True)
    incoming_ignored = Column(Boolean, default=False, nullable=False)
    no_message = Column(Boolean, default=False, nullable=False)
    no_message_reason = Column(String(80), nullable=True)
    ui_tag = Column(String(64), nullable=True)
    ivr_intent = Column(String(100), nullable=True)
    # Seul JSON autorise (karaoke SRT)
    transcription_cues = Column(JsonbCompat, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    caller = relationship("Caller", back_populates="calls")
    client = relationship("Client", back_populates="calls")
    voicemails = relationship("Voicemail", back_populates="call")

    @property
    def extra_data(self) -> Optional[dict]:
        """
        Vue derivee read-only pour l'API / front (anciennement colonne JSON metadata).

        @returns Dict des champs a plat non vides, ou None.
        """
        data: dict = {}
        if self.incoming_profile:
            data["incoming_profile"] = self.incoming_profile
        if self.incoming_policy_source:
            data["incoming_policy_source"] = self.incoming_policy_source
        if self.incoming_rings is not None:
            data["incoming_rings"] = self.incoming_rings
        if self.incoming_ignored:
            data["incoming_ignored"] = True
        if self.no_message:
            data["no_message"] = True
        if self.no_message_reason:
            data["no_message_reason"] = self.no_message_reason
        if self.ui_tag:
            data["ui_tag"] = self.ui_tag
        if self.ivr_intent:
            data["ivr_intent"] = self.ivr_intent
        if self.transcription_cues is not None:
            data["transcription_cues"] = self.transcription_cues
        return data or None


class Voicemail(Base):
    """Modele pour les messages vocaux (cues SRT optionnels en JSONB)."""

    __tablename__ = "voicemails"
    __table_args__ = (
        Index("ix_voicemails_created_at", "created_at"),
        Index("ix_voicemails_read_archived_created", "is_read", "is_archived", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="CASCADE"), nullable=True, index=True)
    caller_id = Column(Integer, ForeignKey("callers.id", ondelete="SET NULL"), nullable=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)

    phone_number = Column(String(20), index=True, nullable=True)
    caller_name = Column(String(255), nullable=True)

    audio_file = Column(String(500), nullable=False)
    transcription = Column(Text, nullable=True)
    transcription_cues = Column(JsonbCompat, nullable=True)
    duration = Column(Integer, nullable=True)

    is_read = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    call = relationship("Call", back_populates="voicemails")
    caller = relationship("Caller")
    client = relationship("Client", back_populates="voicemails")


class BlockRule(Base):
    """Modèle pour les règles de blocage"""
    
    __tablename__ = "block_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    pattern = Column(String(255), nullable=False)  # Pattern regex ou numéro exact
    pattern_type = Column(String(50), default="regex")  # regex, exact, prefix
    
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PhoneNumberProfile(Base):
    """Modele pour les profils OSINT des numeros (champs structures, sans dump JSON)."""

    __tablename__ = "phone_number_profiles"
    __table_args__ = (
        UniqueConstraint("normalized_number", name="uq_phone_number_profiles_normalized"),
    )

    id = Column(Integer, primary_key=True, index=True)

    phone_number = Column(String(32), index=True, nullable=False)
    normalized_number = Column(String(32), nullable=False)

    caller_id = Column(Integer, ForeignKey("callers.id", ondelete="SET NULL"), nullable=True, index=True)

    country = Column(String(64), nullable=True)
    region = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    department = Column(String(64), nullable=True)
    postal_code = Column(String(16), nullable=True)
    line_type = Column(String(32), nullable=True)
    operator = Column(String(128), nullable=True)
    carrier = Column(String(128), nullable=True)

    is_company = Column(Boolean, default=False, nullable=False)
    name = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)

    reputation = Column(String(32), nullable=True, index=True)
    is_spam = Column(Boolean, default=False, nullable=False, index=True)
    is_scam = Column(Boolean, default=False, nullable=False, index=True)
    is_commercial = Column(Boolean, default=False, nullable=False)
    is_telemarketer = Column(Boolean, default=False, nullable=False)
    confidence = Column(Integer, nullable=True)

    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    caller = relationship("Caller")


class Client(Base):
    """Contact / personne rattachee a une entreprise."""
    
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    
    entreprise_id = Column(Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), nullable=True, index=True)
    phone_number = Column(String(20), index=True, nullable=False)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    entreprise = relationship("Entreprise")
    calls = relationship("Call", back_populates="client")
    voicemails = relationship("Voicemail", back_populates="client")
    agenda_items = relationship("Appointment", back_populates="client")
    quotes = relationship("Quote", back_populates="client")


class Entreprise(Base):
    """Modele pour les entreprises importees (prospection)."""

    __tablename__ = "entreprises"
    __table_args__ = (
        Index("ix_entreprises_created_at", "created_at"),
        Index("ix_entreprises_country", "country"),
    )

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), nullable=False, index=True)

    # Website present dans les sources, mais par regle metier on importera surtout celles sans site.
    website = Column(String(500), nullable=True)

    phone_number = Column(String(64), nullable=True)
    phone_digits = Column(String(64), nullable=True, index=True)  # Pour dedup/lookup tolerant

    country = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True, index=True)
    address_1 = Column(String(500), nullable=True)
    address_2 = Column(String(500), nullable=True)

    longitude = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)

    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations techniques
    import_rows = relationship("EntrepriseImportRow", back_populates="entreprise")
    phone_analyses = relationship("EntreprisePhoneAnalysis", back_populates="entreprise")
    categories = relationship(
        "EntrepriseCategory",
        secondary=entreprise_category_links,
        back_populates="entreprises",
        collection_class=set,
    )
    emails = relationship(
        "EntrepriseEmail",
        secondary=entreprise_email_links,
        back_populates="entreprises",
        collection_class=set,
    )


class EntrepriseEmail(Base):
    """Email normalise reutilisable en relation M2M avec les entreprises."""

    __tablename__ = "entreprise_emails"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entreprises = relationship(
        "Entreprise",
        secondary=entreprise_email_links,
        back_populates="emails",
        collection_class=set,
    )


class EntrepriseCategory(Base):
    """Categorie normalisee d'entreprise (M2M)."""

    __tablename__ = "entreprise_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    entreprises = relationship(
        "Entreprise",
        secondary=entreprise_category_links,
        back_populates="categories",
        collection_class=set,
    )


class EntrepriseImportBatch(Base):
    """Lot d'import (un fichier) et son resume."""

    __tablename__ = "entreprise_import_batches"

    id = Column(Integer, primary_key=True, index=True)

    original_filename = Column(String(500), nullable=True)
    source = Column(String(64), nullable=False, default="excel")

    total_rows = Column(Integer, nullable=False, default=0)
    imported_rows = Column(Integer, nullable=False, default=0)
    skipped_with_website = Column(Integer, nullable=False, default=0)
    skipped_invalid = Column(Integer, nullable=False, default=0)
    skipped_duplicates = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    rows = relationship(
        "EntrepriseImportRow",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class EntrepriseImportRow(Base):
    """Ligne d'import (traçabilité et erreurs)."""

    __tablename__ = "entreprise_import_rows"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("entreprise_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)

    # Ligne source normalisee (colonnes pertinentes)
    name = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    phone_number = Column(String(64), nullable=True)
    country = Column(String(128), nullable=True)
    address_1 = Column(String(500), nullable=True)
    address_2 = Column(String(500), nullable=True)
    category = Column(String(255), nullable=True)

    status = Column(String(32), nullable=False, default="pending")  # imported, skipped_website, skipped_invalid, skipped_duplicate
    reason = Column(String(500), nullable=True)

    entreprise_id = Column(Integer, ForeignKey("entreprises.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("EntrepriseImportBatch", back_populates="rows")
    entreprise = relationship("Entreprise", back_populates="import_rows")


class EntreprisePhoneAnalysis(Base):
    """Lien technique entre une entreprise et une analyse OSINT de numero."""

    __tablename__ = "entreprise_phone_analyses"

    id = Column(Integer, primary_key=True, index=True)
    entreprise_id = Column(Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), nullable=False, index=True)

    phone_number = Column(String(64), nullable=False)
    phone_digits = Column(String(64), nullable=True, index=True)

    # Lien vers le profil OSINT persiste (existant dans VocalGuard)
    # On ne cascade PAS la suppression du profil (peut être partagé par d'autres usages: appels, autres entreprises).
    # En revanche, si un profil est supprimé, on nettoie la référence.
    phone_profile_id = Column(Integer, ForeignKey("phone_number_profiles.id", ondelete="SET NULL"), nullable=True, index=True)

    status = Column(String(32), nullable=False, default="queued")  # queued, done, failed
    error_message = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entreprise = relationship("Entreprise", back_populates="phone_analyses")
    phone_profile = relationship("PhoneNumberProfile")


class Appointment(Base):
    """Modele pour les rendez-vous."""
    
    __tablename__ = "agenda"
    __table_args__ = (
        Index("ix_agenda_start_time", "start_time"),
        Index("ix_agenda_created_at", "created_at"),
    )
    
    id = Column(Integer, primary_key=True, index=True)
    
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    source_call_id = Column(Integer, ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True)
    entreprise_id = Column(Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), nullable=True, index=True)
    phone_number = Column(String(20), index=True, nullable=True)
    
    title = Column(String(255), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="scheduled")
    service_type = Column(String(100), nullable=True)
    agenda_tag = Column(String(50), nullable=True)
    display_icon = Column(String(50), nullable=True)
    display_color = Column(String(20), nullable=True)
    is_all_day = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    client = relationship("Client", back_populates="agenda_items")
    source_call = relationship("Call")
    entreprise = relationship("Entreprise")


class AppointmentSettings(Base):
    """Parametres globaux d'agenda (horaires de travail et duree par defaut)."""

    __tablename__ = "appointment_settings"

    id = Column(Integer, primary_key=True, index=True)
    timezone = Column(String(64), nullable=False, default="Europe/Paris")
    work_day_start = Column(Time, nullable=False)
    work_day_end = Column(Time, nullable=False)
    slot_minutes = Column(Integer, nullable=False, default=60)
    monday_enabled = Column(Boolean, nullable=False, default=True)
    tuesday_enabled = Column(Boolean, nullable=False, default=True)
    wednesday_enabled = Column(Boolean, nullable=False, default=True)
    thursday_enabled = Column(Boolean, nullable=False, default=True)
    friday_enabled = Column(Boolean, nullable=False, default=True)
    saturday_enabled = Column(Boolean, nullable=False, default=False)
    sunday_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppointmentNonWorkingDay(Base):
    """Journee indisponible (ferie, conge, fermeture exceptionnelle)."""

    __tablename__ = "appointment_non_working_days"
    __table_args__ = (
        UniqueConstraint("date", name="uq_appointment_non_working_day_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    label = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Quote(Base):
    """Modele pour les devis (lignes en table enfant quote_lines)."""

    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)

    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(20), index=True, nullable=True)

    title = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False)

    # Montants en centimes pour eviter les flottants
    total_ht = Column(Integer, nullable=True)
    total_ttc = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    client = relationship("Client", back_populates="quotes")
    lines = relationship(
        "QuoteLine",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteLine.position",
    )


class QuoteLine(Base):
    """Ligne de devis (remplace quotes.lines JSON)."""

    __tablename__ = "quote_lines"
    __table_args__ = (
        Index("ix_quote_lines_quote_id", "quote_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    description = Column(String(500), nullable=False)
    quantity = Column(Float, nullable=False, default=1.0)
    unit_price = Column(Float, nullable=False, default=0.0)

    quote = relationship("Quote", back_populates="lines")


class ApiPublicToken(Base):
    """Token d'authentification pour les endpoints publics."""

    __tablename__ = "api_public_tokens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    app_url = Column(String(500), nullable=True)
    token = Column(String(128), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    can_read_agenda = Column(Boolean, nullable=False, default=True)
    can_write_agenda = Column(Boolean, nullable=False, default=True)
    can_write_entreprises = Column(Boolean, nullable=False, default=True)
    can_manage_tokens = Column(Boolean, nullable=False, default=False)
    can_read_customers = Column(Boolean, nullable=False, default=False)
    can_write_customers = Column(Boolean, nullable=False, default=False)
    can_read_quotes = Column(Boolean, nullable=False, default=False)
    can_write_quotes = Column(Boolean, nullable=False, default=False)
    can_read_calls = Column(Boolean, nullable=False, default=False)
    can_read_voicemails = Column(Boolean, nullable=False, default=False)
    can_write_calls = Column(Boolean, nullable=False, default=False)
    can_subscribe_realtime = Column(Boolean, nullable=False, default=False)
    can_write_trusted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class MobilePairingSession(Base):
    """Session d appairage mobile ephemere (QR code)."""

    __tablename__ = "mobile_pairing_sessions"

    id = Column(Integer, primary_key=True, index=True)
    code_hash = Column(String(128), unique=True, nullable=False, index=True)
    api_token_id = Column(Integer, ForeignKey("api_public_tokens.id", ondelete="CASCADE"), nullable=False)
    base_url = Column(String(500), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    claimed_device_hint = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Intent(Base):
    """
    Intent conversationnel (repondeur / KB).

    Source de verite runtime : tables normalisees (pas de JSON metier).
    """

    __tablename__ = "intents"
    __table_args__ = (Index("ix_intents_enabled_priority", "enabled", "priority"),)

    id = Column(Integer, primary_key=True, index=True)
    tag = Column(String(100), unique=True, nullable=False, index=True)
    source = Column(String(40), nullable=False, default="seed")
    niveau = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=10)
    wav_basename = Column(String(120), nullable=True)
    action = Column(String(60), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    patterns = relationship(
        "IntentPattern",
        back_populates="intent",
        cascade="all, delete-orphan",
    )
    responses = relationship(
        "IntentResponse",
        back_populates="intent",
        cascade="all, delete-orphan",
        order_by="IntentResponse.position",
    )
    embeddings = relationship(
        "IntentEmbedding",
        back_populates="intent",
        cascade="all, delete-orphan",
    )


class IntentPattern(Base):
    """Pattern / utterance d'entrainement ou de boost lexical pour un intent."""

    __tablename__ = "intent_patterns"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(
        Integer,
        ForeignKey("intents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pattern = Column(Text, nullable=False)
    weight = Column(Float, nullable=False, default=1.0)

    intent = relationship("Intent", back_populates="patterns")


class IntentResponse(Base):
    """Texte de reponse vocale (TTS / WAV cache) pour un intent."""

    __tablename__ = "intent_responses"

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(
        Integer,
        ForeignKey("intents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False)

    intent = relationship("Intent", back_populates="responses")


class IntentEmbedding(Base):
    """
    Embedding vectoriel d'un pattern ou d'une reponse.

    Sur Postgres + pgvector : colonne ``embedding`` type vector.
    En fallback / SQLite tests : ``embedding_json`` (liste de floats).
    """

    __tablename__ = "intent_embeddings"
    __table_args__ = (
        UniqueConstraint("ref_type", "ref_id", name="uq_intent_embeddings_ref"),
    )

    id = Column(Integer, primary_key=True, index=True)
    intent_id = Column(
        Integer,
        ForeignKey("intents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ref_type = Column(String(20), nullable=False)  # pattern | response
    ref_id = Column(Integer, nullable=False)
    # Stockage portable (toujours) ; pgvector lit aussi via SQL natif.
    embedding_json = Column(JsonbCompat, nullable=False, default=list)
    dim = Column(Integer, nullable=False, default=384)

    intent = relationship("Intent", back_populates="embeddings")


class CallLead(Base):
    """Coordonnees / lead collecte pendant un appel conversationnel."""

    __tablename__ = "call_leads"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True)
    phone_number = Column(String(40), nullable=True, index=True)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    callback_phone = Column(String(40), nullable=True)
    notes = Column(Text, nullable=True)
    intent_tag = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

