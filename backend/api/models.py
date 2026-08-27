"""
Modèles Pydantic pour l'API
"""

from datetime import datetime, date, time, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_serializer


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """Serialise un datetime naif (stocke UTC) avec suffixe Z pour le front."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


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

    @field_serializer("call_time", "answer_time", "end_time")
    def serialize_call_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        """Expose les horodatages UTC avec Z (evite le decalage navigateur)."""
        return _utc_iso(value)

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

    @field_serializer("created_at")
    def serialize_created_at(self, value: Optional[datetime]) -> Optional[str]:
        """Expose created_at UTC avec Z (evite le decalage navigateur)."""
        return _utc_iso(value)
    
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
    
    client_id: Optional[int] = None
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

    client_id: Optional[int] = None
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
    
    client_id: Optional[int] = None
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


# (Rebuild pydantic model refs)
QuoteResponse.model_rebuild()


class ClientBase(BaseModel):
    """Informations de base sur un client (personne)."""

    entreprise_id: Optional[int] = None
    phone_number: str
    email: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None


class ClientCreate(ClientBase):
    """Creation d'un client."""


class ClientResponse(ClientBase):
    """Client retourne par l'API."""
    
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Backward compatibility (ancien nom)
CustomerBase = ClientBase
CustomerCreate = ClientCreate
CustomerResponse = ClientResponse


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
    emails: List[str] = []


class EntrepriseCreate(EntrepriseBase):
    """Creation manuelle d'une entreprise."""


class EntrepriseUpdate(BaseModel):
    """Mise a jour d'une entreprise."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
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
    emails: Optional[List[str]] = None


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


class PublicApiTokenCreate(BaseModel):
    """Creation d'un token API public."""

    app_url: str = Field(..., min_length=3, max_length=500)
    name: Optional[str] = Field(default=None, max_length=255)
    can_read_agenda: bool = True
    can_write_agenda: bool = True
    can_write_entreprises: bool = True
    can_manage_tokens: bool = False
    can_read_customers: bool = False
    can_write_customers: bool = False
    can_read_quotes: bool = False
    can_write_quotes: bool = False
    can_read_calls: bool = False


class PublicApiTokenResponse(BaseModel):
    """Token API public retourne par l'API."""

    id: int
    name: str
    app_url: Optional[str] = None
    token: Optional[str] = None
    token_preview: Optional[str] = None
    is_active: bool
    can_read_agenda: bool
    can_write_agenda: bool
    can_write_entreprises: bool
    can_manage_tokens: bool
    can_read_customers: bool = False
    can_write_customers: bool = False
    can_read_quotes: bool = False
    can_write_quotes: bool = False
    can_read_calls: bool = False
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PublicApiTokenUpdate(BaseModel):
    """Mise a jour d'un token API public (merge)."""

    name: Optional[str] = Field(default=None, max_length=255)
    app_url: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    can_read_agenda: Optional[bool] = None
    can_write_agenda: Optional[bool] = None
    can_write_entreprises: Optional[bool] = None
    can_manage_tokens: Optional[bool] = None
    can_read_customers: Optional[bool] = None
    can_write_customers: Optional[bool] = None
    can_read_quotes: Optional[bool] = None
    can_write_quotes: Optional[bool] = None
    can_read_calls: Optional[bool] = None


class PublicAgendaBookingCreate(BaseModel):
    """Payload formulaire public pour reserver un creneau agenda."""

    preferred_date: date
    preferred_time: str = Field(..., min_length=4, max_length=5, pattern=r"^\d{2}:\d{2}$")
    service: Optional[str] = None
    budget: Optional[str] = None
    project_type: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=255)
    company_name: Optional[str] = Field(None, max_length=255)
    website: Optional[str] = Field(None, max_length=500)
    city: Optional[str] = Field(None, max_length=128)
    country: Optional[str] = Field(None, max_length=128)
    address_1: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=255)
    emails: List[str] = []
    phone: Optional[str] = Field(None, max_length=64)
    message: Optional[str] = None


class SettingsResponse(BaseModel):
    """Configuration metier exposee au frontend."""

    database_url: str
    api_host: str
    api_port: int
    modem_port: Optional[str] = None
    voice_language: str
    rings_before_answer: int
    voicemail_enabled: bool
    incoming_auto_answer: bool = True
    # voicemail = repondeur coupe-sonnerie ; phone = telephone parallele seul
    incoming_line_mode: Literal["voicemail", "phone"] = "voicemail"


class TelephonyStatusResponse(BaseModel):
    """Etat telephonie pour pastille UI (modem / daemon)."""

    status: str = "unknown"
    modem_initialized: bool = False
    modem_port: Optional[str] = None
    firmware_ati3: Optional[str] = None
    last_ring_at: Optional[float] = None
    last_cid_raw: Optional[str] = None
    last_error: Optional[str] = None
    incoming_line_mode: Literal["voicemail", "phone"] = "voicemail"
    in_call: bool = False
    relay_failures: int = 0
    last_incoming_decision: Optional[str] = None


class IncomingLineModeUpdate(BaseModel):
    """Basculer entre repondeur modem et telephone parallele."""

    mode: Literal["voicemail", "phone"] = Field(
        ...,
        description="voicemail: modem decroche (coupe sonnerie). phone: fixe seul.",
    )


class IncomingCallConfigResponse(BaseModel):
    """Configuration complete des appels entrants (effective + presets)."""

    incoming_line_mode: Literal["voicemail", "phone"] = "voicemail"
    cid_wait_sec: float = 2.5
    instant_seize_cid_grace_sec: float = 0.35
    ring_cycle_sec: float = 6.0
    ring_quiet_abort_sec: float = 6.0
    max_incoming_wait_sec: float = 45.0
    phone_mode_rings: int = 4
    whitelist_ring_only: bool = False
    whitelist_match: Literal["exact", "prefix", "e164_normalize"] = "exact"
    screened_when_unknown: bool = True
    active_preset: Literal["voicemail", "phone"] = "voicemail"
    presets: Dict[str, Any] = Field(default_factory=dict)
    profiles: Dict[str, Any] = Field(default_factory=dict)
    profile_overrides: Dict[str, Any] = Field(default_factory=dict)
    audio: Dict[str, Any] = Field(default_factory=dict)
    voicemail: Dict[str, Any] = Field(default_factory=dict)
    number_patterns: Dict[str, Any] = Field(default_factory=dict)
    advanced: Dict[str, Any] = Field(default_factory=dict)
    rings_before_answer: int = 0
    incoming_auto_answer: bool = True


class IncomingCallConfigPatch(BaseModel):
    """Patch partiel de la configuration appels entrants."""

    cid_wait_sec: Optional[float] = Field(None, ge=0.0, le=30.0)
    instant_seize_cid_grace_sec: Optional[float] = Field(None, ge=0.0, le=5.0)
    ring_cycle_sec: Optional[float] = Field(None, ge=3.0, le=15.0)
    ring_quiet_abort_sec: Optional[float] = Field(None, ge=2.0, le=20.0)
    max_incoming_wait_sec: Optional[float] = Field(None, ge=10.0, le=120.0)
    phone_mode_rings: Optional[int] = Field(None, ge=0, le=20)
    whitelist_ring_only: Optional[bool] = None
    whitelist_match: Optional[Literal["exact", "prefix", "e164_normalize"]] = None
    screened_when_unknown: Optional[bool] = None
    presets: Optional[Dict[str, Any]] = None
    profiles: Optional[Dict[str, Any]] = None
    profile_overrides: Optional[Dict[str, Any]] = None
    audio: Optional[Dict[str, Any]] = None
    voicemail: Optional[Dict[str, Any]] = None
    number_patterns: Optional[Dict[str, Any]] = None
    advanced: Optional[Dict[str, Any]] = None


class MobileClaimRequest(BaseModel):
    """Echange d'un code QR d'appairage mobile contre un token API."""

    code: str = Field(..., min_length=1, max_length=64)
    device_hint: Optional[str] = Field(None, max_length=255)


class MobileClaimResponse(BaseModel):
    """Reponse claim mobile : token Bearer + URL + permissions."""

    token: str
    base_url: str
    permissions: Dict[str, bool] = Field(default_factory=dict)


class TrustedContactItem(BaseModel):
    """Contact a importer en personne de confiance."""

    phone_number: str = Field(..., min_length=3, max_length=64)
    name: Optional[str] = Field(None, max_length=255)


class TrustedContactImportRequest(BaseModel):
    """Import batch de contacts de confiance depuis l'app mobile."""

    contacts: List[TrustedContactItem] = Field(default_factory=list)


class MobilePairingSessionCreate(BaseModel):
    """Creation d'une session QR d'appairage mobile."""

    base_url: str = Field(..., min_length=1, max_length=512)
    api_token_id: Optional[int] = None
    create_token_if_missing: bool = False
    token_name: Optional[str] = Field(None, max_length=255)


class MobilePairingSessionResponse(BaseModel):
    """Session d'appairage ephemere (code + URI QR)."""

    pairing_id: int
    code: str
    expires_at: datetime
    qr_uri: str


class UiLoginRequest(BaseModel):
    """Connexion UI web (mot de passe partage)."""

    password: str = Field(..., min_length=1, max_length=256)


class DailyStatsItem(BaseModel):
    """Stats par jour pour les graphiques (volume d'appels, RDV, devis, blocages, messages)."""
    day: str  # Libelle court : Lun, Mar, ...
    date: str  # ISO date pour coherence
    calls: int = 0
    rdv: int = 0
    quotes: int = 0
    spam: int = 0
    voicemails: int = 0


class DashboardStatsResponse(BaseModel):
    """Stats du dashboard : cartes + donnees pour graphiques (valeurs reelles backend)."""
    calls_today: int = 0
    rdv_count: int = 0
    quotes_count: int = 0
    suspects_count: int = 0
    total_calls: int = 0
    total_blocked: int = 0
    voicemails_today: int = 0
    voicemails_unread: int = 0
    voicemails_total: int = 0
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


