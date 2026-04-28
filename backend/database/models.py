"""
Modèles de base de données SQLAlchemy
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float, Table
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

entreprise_category_links = Table(
    "entreprise_category_links",
    Base.metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("entreprise_categories.id", ondelete="CASCADE"), primary_key=True),
)


class Caller(Base):
    """Modèle pour les appelants"""
    
    __tablename__ = "callers"
    
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    is_blocked = Column(Boolean, default=False)
    is_whitelisted = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    extra_data = Column("metadata", JSON, nullable=True)  # Données supplémentaires (score, tags, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    calls = relationship("Call", back_populates="caller")


class FrenchPhonePrefix(Base):
    """Modèle pour les préfixes de numéros français"""
    
    __tablename__ = "french_phone_prefixes"
    
    id = Column(Integer, primary_key=True, index=True)
    prefix = Column(String(10), unique=True, index=True, nullable=False)  # Ex: 0387
    city = Column(String(255), nullable=True)
    region = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    postal_code = Column(String(10), nullable=True)
    operator = Column(String(100), nullable=True)
    operator_type = Column(String(50), nullable=True)  # historique, alternatif
    line_type = Column(String(20), nullable=True)  # mobile, landline, special
    latitude = Column(String(20), nullable=True)
    longitude = Column(String(20), nullable=True)
    population = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Call(Base):
    """Modèle pour les appels"""
    
    __tablename__ = "calls"
    
    id = Column(Integer, primary_key=True, index=True)
    caller_id = Column(Integer, ForeignKey("callers.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    phone_number = Column(String(20), index=True, nullable=True)
    caller_name = Column(String(255), nullable=True)
    
    call_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    answer_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    
    status = Column(String(50), default="ringing")  # ringing, answered, blocked, completed, missed
    duration = Column(Integer, nullable=True)  # Durée en secondes
    
    transcription = Column(Text, nullable=True)  # Transcription de l'appel
    audio_file = Column(String(500), nullable=True)  # Chemin du fichier audio
    
    extra_data = Column("metadata", JSON, nullable=True)  # Données supplémentaires
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    caller = relationship("Caller", back_populates="calls")
    customer = relationship("Customer", back_populates="calls")


class Voicemail(Base):
    """Modèle pour les messages vocaux"""
    
    __tablename__ = "voicemails"
    
    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=True)
    caller_id = Column(Integer, ForeignKey("callers.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    
    phone_number = Column(String(20), index=True, nullable=True)
    caller_name = Column(String(255), nullable=True)
    
    audio_file = Column(String(500), nullable=False)
    transcription = Column(Text, nullable=True)
    duration = Column(Integer, nullable=True)  # Durée en secondes
    
    is_read = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relations
    call = relationship("Call")
    caller = relationship("Caller")
    customer = relationship("Customer", back_populates="voicemails")


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
    """Modele pour les profils OSINT des numeros."""
    
    __tablename__ = "phone_number_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Numero tel tel que vu dans les appels
    phone_number = Column(String(32), index=True, nullable=False)
    # Numero normalise (ex: format E.164) pour dedoublonnage
    normalized_number = Column(String(32), index=True, nullable=False)
    
    caller_id = Column(Integer, ForeignKey("callers.id"), nullable=True)
    
    # Informations basiques
    country = Column(String(64), nullable=True)
    region = Column(String(128), nullable=True)
    city = Column(String(128), nullable=True)
    department = Column(String(64), nullable=True)
    postal_code = Column(String(16), nullable=True)
    line_type = Column(String(32), nullable=True)
    operator = Column(String(128), nullable=True)
    carrier = Column(String(128), nullable=True)
    
    # Identite / entreprise
    is_company = Column(Boolean, default=False)
    name = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    
    # Reputation
    reputation = Column(String(32), nullable=True)
    is_spam = Column(Boolean, default=False)
    is_scam = Column(Boolean, default=False)
    is_commercial = Column(Boolean, default=False)
    is_telemarketer = Column(Boolean, default=False)
    # Confiance en pourcentage (0 - 100)
    confidence = Column(Integer, nullable=True)
    
    # Donnees brutes renvoyees par les outils OSINT
    raw_data = Column(JSON, nullable=True)
    
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    caller = relationship("Caller")


class Customer(Base):
    """Modele pour les clients / contacts DanielCraftFr."""
    
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    
    phone_number = Column(String(20), index=True, nullable=False)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    calls = relationship("Call", back_populates="customer")
    voicemails = relationship("Voicemail", back_populates="customer")
    appointments = relationship("Appointment", back_populates="customer")
    quotes = relationship("Quote", back_populates="customer")


class Entreprise(Base):
    """Modele pour les entreprises importees (prospection)."""

    __tablename__ = "entreprises"

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
    
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    phone_number = Column(String(20), index=True, nullable=True)
    
    title = Column(String(255), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    location = Column(String(255), nullable=True)
    status = Column(String(50), default="scheduled")
    service_type = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer", back_populates="appointments")


class Quote(Base):
    """Modele pour les devis."""
    
    __tablename__ = "quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    phone_number = Column(String(20), index=True, nullable=True)
    
    title = Column(String(255), nullable=False)
    lines = Column(JSON, nullable=False)  # Liste de lignes serializee
    notes = Column(Text, nullable=True)
    status = Column(String(50), default="draft")
    
    # Montants en centimes pour eviter les flottants
    total_ht = Column(Integer, nullable=True)
    total_ttc = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer", back_populates="quotes")

