"""
Modèles Pydantic pour l'API
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
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
    phone_number: Optional[str] = None
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    status: str = "scheduled"
    service_type: Optional[str] = None
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    """Creation d'un rendez-vous."""


class AppointmentResponse(AppointmentBase):
    """Rendez-vous retourne par l'API."""
    
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


