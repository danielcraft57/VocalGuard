"""
Modèles Pydantic pour l'API
"""

from datetime import datetime, date, time
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class CallResponse(BaseModel):
    """Modèle de réponse pour un appel"""
    id: int
    caller_id: Optional[int] = None
    phone_number: Optional[str] = None
    caller_name: Optional[str] = None
    call_time: datetime
    answer_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: str
    duration: Optional[int] = None
    transcription: Optional[str] = None
    audio_file: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    osint: Optional["OsintReputationResponse"] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        """Compatibilité avec Pydantic v1"""
        return cls.model_validate(obj)


class CallListResponse(BaseModel):
    """Modèle de réponse pour une liste d'appels"""
    total: int
    skip: int
    limit: int
    calls: List[CallResponse]


class CallerResponse(BaseModel):
    """Modèle de réponse pour un appelant"""
    id: int
    phone_number: str
    name: Optional[str] = None
    is_blocked: bool
    is_whitelisted: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Compatibilité avec Pydantic v1"""
        return cls.model_validate(obj)


class CallerCreate(BaseModel):
    """Modèle pour créer un appelant"""
    phone_number: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = None
    is_blocked: bool = False
    is_whitelisted: bool = False
    notes: Optional[str] = None


class CallerUpdate(BaseModel):
    """Modèle pour mettre à jour un appelant"""
    name: Optional[str] = None
    is_blocked: Optional[bool] = None
    is_whitelisted: Optional[bool] = None
    notes: Optional[str] = None


class WhitelistAddRequest(BaseModel):
    """Corps pour ajouter un numéro à la liste blanche (inspiré callattendant Permitted)."""
    phone_number: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class BlockAddRequest(BaseModel):
    """Corps pour ajouter un numéro à la liste noire (inspiré callattendant Blocked)."""
    phone_number: str = Field(..., min_length=1, max_length=20)
    name: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class VoicemailResponse(BaseModel):
    """Modèle de réponse pour un message vocal"""
    id: int
    call_id: Optional[int] = None
    caller_id: Optional[int] = None
    phone_number: Optional[str] = None
    caller_name: Optional[str] = None
    audio_file: str
    transcription: Optional[str] = None
    duration: Optional[int] = None
    is_read: bool
    is_archived: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Compatibilité avec Pydantic v1"""
        return cls.model_validate(obj)


class PhoneNumberProfileResponse(BaseModel):
    """Profil OSINT persiste d'un numero de telephone."""
    
    id: int
    phone_number: str
    normalized_number: str
    
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    postal_code: Optional[str] = None
    line_type: Optional[str] = None
    operator: Optional[str] = None
    carrier: Optional[str] = None
    
    is_company: bool = False
    name: Optional[str] = None
    company_name: Optional[str] = None
    
    reputation: Optional[str] = None
    is_spam: bool = False
    is_scam: bool = False
    is_commercial: bool = False
    is_telemarketer: bool = False
    confidence: Optional[int] = None
    
    last_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    raw_data: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """Compatibilite avec Pydantic v1."""
        return cls.model_validate(obj)


class OsintReputationResponse(BaseModel):
    """Reponse typee pour la reputation d'un numero (optionnellement lieu et operateur)."""

    phone_number: str
    reputation: str = "unknown"
    is_spam: bool = False
    is_scam: bool = False
    is_commercial: bool = False
    is_telemarketer: bool = False
    confidence: float = 0.0
    sources: List[str] = []
    recommendation: str = "review"
    city: Optional[str] = None
    region: Optional[str] = None
    operator: Optional[str] = None


# Resoudre la reference forward dans CallResponse (osint: Optional[OsintReputationResponse])
CallResponse.model_rebuild()


class AppointmentBase(BaseModel):
    """Champs communs pour un rendez-vous."""
    
    customer_id: Optional[int] = None
    source_call_id: Optional[int] = None
    entreprise_id: Optional[int] = None
    phone_number: Optional[str] = None
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    status: str = "scheduled"
    service_type: Optional[str] = None
    agenda_tag: Optional[str] = None
    display_icon: Optional[str] = None
    display_color: Optional[str] = None
    is_all_day: bool = False
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    """Creation d'un rendez-vous."""


class AppointmentResponse(AppointmentBase):
    """Rendez-vous retourne par l'API."""
    
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class AppointmentUpdate(BaseModel):
    """Mise a jour partielle d'un rendez-vous."""

    customer_id: Optional[int] = None
    entreprise_id: Optional[int] = None
    phone_number: Optional[str] = None
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    service_type: Optional[str] = None
    agenda_tag: Optional[str] = None
    display_icon: Optional[str] = None
    display_color: Optional[str] = None
    is_all_day: Optional[bool] = None
    notes: Optional[str] = None


class AppointmentSettingsBase(BaseModel):
    """Configuration de disponibilite agenda."""

    timezone: str = "Europe/Paris"
    work_day_start: time = Field(default=time(hour=8, minute=30))
    work_day_end: time = Field(default=time(hour=18, minute=0))
    slot_minutes: int = Field(default=60, ge=15, le=480)
    monday_enabled: bool = True
    tuesday_enabled: bool = True
    wednesday_enabled: bool = True
    thursday_enabled: bool = True
    friday_enabled: bool = True
    saturday_enabled: bool = False
    sunday_enabled: bool = False


class AppointmentSettingsResponse(AppointmentSettingsBase):
    """Parametres agenda retournes par l'API."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AppointmentNonWorkingDayCreate(BaseModel):
    """Creation d'un jour non travaille."""

    date: date
    label: str = Field(..., min_length=1, max_length=255)


class AppointmentNonWorkingDayResponse(AppointmentNonWorkingDayCreate):
    """Jour non travaille retourne par l'API."""

    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class QuoteLine(BaseModel):
    """Ligne d'un devis."""
    
    description: str
    quantity: float = 1.0
    unit_price: float


class QuoteBase(BaseModel):
    """Champs communs pour un devis."""
    
    customer_id: Optional[int] = None
    phone_number: Optional[str] = None
    title: str
    lines: List[QuoteLine]
    notes: Optional[str] = None
    status: str = "draft"


class QuoteCreate(QuoteBase):
    """Creation d'un devis."""


class QuoteResponse(QuoteBase):
    """Devis retourne par l'API."""
    
    id: int
    total_ht: float
    total_ttc: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class CustomerBase(BaseModel):
    """Informations de base sur un client."""
    
    phone_number: str
    email: Optional[str] = None
    name: Optional[str] = None
    company_name: Optional[str] = None
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    """Creation d'un client."""


class CustomerResponse(CustomerBase):
    """Client retourne par l'API."""
    
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EntrepriseBase(BaseModel):
    """Entreprise (modele metier) - champs principaux."""

    name: str = Field(..., min_length=1, max_length=255)
    website: Optional[str] = Field(None, max_length=500)
    phone_number: Optional[str] = Field(None, max_length=64)
    country: Optional[str] = Field(None, max_length=128)
    city: Optional[str] = Field(None, max_length=128)
    address_1: Optional[str] = Field(None, max_length=500)
    address_2: Optional[str] = Field(None, max_length=500)
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None


class EntrepriseCreate(EntrepriseBase):
    """Creation manuelle d'une entreprise."""


class EntrepriseResponse(EntrepriseBase):
    """Entreprise retournee par l'API."""

    id: int
    phone_digits: Optional[str] = None
    categories: List[str] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EntrepriseListResponse(BaseModel):
    """Liste paginée d'entreprises (pour UI)."""

    total: int
    skip: int
    limit: int
    items: List[EntrepriseResponse]


class EntrepriseImportSummary(BaseModel):
    """Resume d'un import (Excel)."""

    batch_id: int
    original_filename: Optional[str] = None
    total_rows: int = 0
    imported_rows: int = 0
    skipped_with_website: int = 0
    skipped_invalid: int = 0
    skipped_duplicates: int = 0


class EntrepriseImportRowResponse(BaseModel):
    """Ligne d'import (traçabilite)."""

    id: int
    batch_id: int
    row_number: int
    name: Optional[str] = None
    website: Optional[str] = None
    phone_number: Optional[str] = None
    country: Optional[str] = None
    address_1: Optional[str] = None
    address_2: Optional[str] = None
    category: Optional[str] = None
    status: Literal["pending", "imported", "skipped_website", "skipped_invalid", "skipped_duplicate"]
    reason: Optional[str] = None
    entreprise_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EntreprisePhoneAnalysisResponse(BaseModel):
    """Etat d'analyse OSINT d'un numero pour une entreprise."""

    id: int
    entreprise_id: int
    phone_number: str
    phone_digits: Optional[str] = None
    phone_profile_id: Optional[int] = None
    status: Literal["queued", "done", "failed"]
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SettingsResponse(BaseModel):
    """Configuration metier exposee au frontend."""
    
    database_url: str
    api_host: str
    api_port: int
    modem_port: Optional[str] = None
    voice_language: str
    rings_before_answer: int
    voicemail_enabled: bool


class DailyStatsItem(BaseModel):
    """Stats par jour pour les graphiques (volume d'appels, RDV, devis, blocages)."""
    day: str  # Libelle court : Lun, Mar, ...
    date: str  # ISO date pour coherence
    calls: int = 0
    rdv: int = 0
    quotes: int = 0
    spam: int = 0


class DashboardStatsResponse(BaseModel):
    """Stats du dashboard : cartes + donnees pour graphiques (valeurs reelles backend)."""
    calls_today: int = 0
    rdv_count: int = 0
    quotes_count: int = 0
    suspects_count: int = 0
    total_calls: int = 0
    total_blocked: int = 0
    daily_series: List["DailyStatsItem"] = []


class BlockRuleResponse(BaseModel):
    """Regle de blocage (pattern exact, prefixe ou regex)."""
    id: int
    name: str
    pattern: str
    pattern_type: str = "regex"
    is_active: bool = True
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BlockRuleCreate(BaseModel):
    """Creation d'une regle de blocage."""
    name: str = Field(..., min_length=1, max_length=255)
    pattern: str = Field(..., min_length=1, max_length=255)
    pattern_type: str = Field(default="regex", pattern="^(exact|prefix|regex)$")
    description: Optional[str] = None


