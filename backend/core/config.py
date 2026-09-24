"""
Configuration de VocalGuard
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml


def _default_base_path() -> Path:
    """Racine du projet : cwd si config/ existe (run depuis VocalGuard), sinon ~/.vocalguard."""
    cwd = Path.cwd()
    if (cwd / "config").exists() or (cwd / "backend").exists():
        return cwd
    return Path.home() / ".vocalguard"


class Config(BaseSettings):
    """Configuration de l'application"""

    # Chemins (BASE_PATH en env pour forcer, sinon auto = repertoire projet si config/ ou backend/ present)
    base_path: Path = Field(default_factory=_default_base_path)
    config_path: Optional[Path] = None
    vg_env: str = Field(default="dev")
    
    # Base de données
    database_url: str = Field(default="sqlite:///vocalguard.db")
    
    # Celery / taches asynchrones
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)
    
    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=False)
    api_public_admin_token: Optional[str] = Field(default=None)
    ui_password: Optional[str] = Field(default=None)
    ui_session_secret: Optional[str] = Field(default=None)
    public_base_url: str = Field(default="http://localhost:8000")
    agenda_public_secret: str = Field(default="change-me")

    # Email SMTP (notifications agenda)
    smtp_host: Optional[str] = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = Field(default=None)
    smtp_password: Optional[str] = Field(default=None)
    smtp_use_tls: bool = Field(default=True)
    smtp_sender: Optional[str] = Field(default=None)
    
    # Modem
    modem_port: Optional[str] = Field(default=None)  # Auto-détection si None
    modem_baudrate: int = Field(default=230400)
    # USR5637 : 129,11025 (16-bit / 11 kHz). Rollback : 128,8000.
    modem_voice_vsm: Optional[str] = Field(default="129,11025")

    # Processus telephony dedie (modem + WebSocket audio sortant) — voir systemd vocalguard-telephony.service
    use_telephony_daemon: bool = Field(default=False)
    telephony_daemon_url: str = Field(default="http://127.0.0.1:8090")
    telephony_public_api_url: str = Field(default="http://127.0.0.1:8000")
    telephony_internal_token: Optional[str] = Field(default=None)
    telephony_bind_host: str = Field(default="127.0.0.1")
    telephony_bind_port: int = Field(default=8090)
    
    # Voice
    voice_recognition_engine: str = Field(default="whisper")  # whisper ou vosk
    voice_synthesis_engine: str = Field(default="pyttsx3")  # pyttsx3, gtts ou edgetts
    voice_language: str = Field(default="fr")
    edge_tts_voice: Optional[str] = Field(default="fr-FR-HenriNeural")  # pour edgetts
    edge_tts_rate: str = Field(default="+0%")  # vitesse IVR edge-tts
    edge_tts_pitch: str = Field(default="+2Hz")  # hauteur edge-tts (ex. +2Hz)
    edge_tts_voice_gain_db: float = Field(default=-6.0)  # niveau voix TTS (dB)

    # ElevenLabs TTS (accueil / KB) — clef via .env uniquement
    elevenlabs_api_key: Optional[str] = Field(default=None)
    elevenlabs_voice_id: Optional[str] = Field(default="JBFqnCBsd6RMkjVDRZzb")
    elevenlabs_model_id: str = Field(default="eleven_multilingual_v2")
    
    # Whisper
    whisper_model: str = Field(default="base")
    whisper_device: str = Field(default="cpu")  # cpu ou cuda
    
    # VOSK
    vosk_model_path: Optional[str] = Field(default=None)

    # Service STT distant (ex. node15.lan:8100) — messages vocaux batch.
    stt_service_url: Optional[str] = Field(default=None)
    stt_internal_token: Optional[str] = Field(default=None)
    # Service TTS distant (ex. node15.lan:8100) — accueil, KB, apercu incoming-audio.
    # Si vide : fallback sur stt_service_url (meme daemon historique).
    tts_service_url: Optional[str] = Field(default=None)

    # Service OSINT distant (ex. node15.lan:8110) — PhoneInfoga / scanners.
    osint_service_url: Optional[str] = Field(default=None)
    osint_internal_token: Optional[str] = Field(default=None)
    
    # Appels
    rings_before_answer: int = Field(default=0)
    # Fenetre pour capter NMBR= avant decision (FR ETSI : entre 1ere et 2e sonnerie).
    cid_wait_sec: float = Field(default=6.0)
    # Delai max (s) avant ATA au 1er RING si rings=0 (laisse passer NMBR= ETSI).
    instant_seize_cid_grace_sec: float = Field(default=5.5)
    # Nombre de sonneries laissees au fixe en mode telephone (UI topbar).
    phone_mode_rings: int = Field(default=4)
    # Mode telephone : apres decroche fixe, greffe silencieuse + enregistrement / STT.
    phone_mode_record: bool = Field(default=True)
    max_call_duration: int = Field(default=300)  # secondes
    # True = le modem decroche (repondeur). False = CID/historique seulement, le fixe gere l'appel.
    incoming_auto_answer: bool = Field(default=True)
    # Planning YAML (voir incoming_line_schedule) : ecrase auto_answer sur creneaux.
    incoming_line_schedule: Optional[dict] = Field(default=None)
    # Si True, les numeros whitelist sonnent au fixe sans ATA modem.
    whitelist_ring_only: bool = Field(default=False)
    # Modem : gains voix (None = ne pas envoyer AT+VGR/VGT).
    modem_voice_vgr: Optional[int] = Field(default=None)
    modem_voice_vgt: Optional[int] = Field(default=None)
    # Code pays ITU T.35 hex (France = 3D). None = ne pas envoyer +GCI.
    modem_country_gci: Optional[str] = Field(default="3D")
    modem_distinctive_ring: bool = Field(default=False)
    modem_pcw_off_for_cid: bool = Field(default=True)
    # Sortant modem : essai AT+VTR (pas VoIP). Defaut false — full-duplex = telephony_backend voip.
    outgoing_use_vtr: bool = Field(default=False)
    # VAD micro sortant (RMS s16le).
    mic_vad_rms: int = Field(default=500)
    mic_vad_hangover_ms: int = Field(default=500)
    # Transport telephonie : modem (prod) | voip (stub loopback) | dual (entrant modem + sortant voip).
    telephony_backend: str = Field(default="modem")
    # Placeholders SIP (vides tant qu'il n'y a pas de compte ; secrets via .env plus tard).
    sip_uri: Optional[str] = Field(default=None)
    sip_user: Optional[str] = Field(default=None)
    sip_password: Optional[str] = Field(default=None)
    sip_realm: Optional[str] = Field(default=None)
    
    # Blocage (inspire de callattendant: NOMOROBO USA, SHOULDIANSWER hors USA, ou vide pour desactiver)
    block_enabled: bool = Field(default=True)
    block_service: str = Field(default="")  # "NOMOROBO", "SHOULDIANSWER", ou "" (desactive)
    # Credentials pour les services de reputation / blocage
    nomorobo_api_key: Optional[str] = Field(default=None)  # X-API-Key pour api.nomorobo.com
    nomorobo_username: Optional[str] = Field(default=None)  # Compatibilite callattendant (legacy)
    nomorobo_password: Optional[str] = Field(default=None)
    shouldianswer_api_key: Optional[str] = Field(default=None)  # Si API disponible a l'avenir
    
    # OSINT - Clés API (optionnel)
    numlookup_api_key: Optional[str] = Field(default=None)
    opencnam_api_key: Optional[str] = Field(default=None)
    numverify_api_key: Optional[str] = Field(default=None)
    hlr_api_key: Optional[str] = Field(default=None)
    
    # Recherche personnes/entreprises
    twilio_account_sid: Optional[str] = Field(default=None)
    twilio_auth_token: Optional[str] = Field(default=None)
    sirene_api_key: Optional[str] = Field(default=None)
    infogreffe_api_key: Optional[str] = Field(default=None)
    
    # Messagerie vocale
    voicemail_enabled: bool = Field(default=True)
    voicemail_mode: str = Field(default="simple")  # simple | ivr | conversation
    voicemail_greeting: str = Field(
        default=(
            "Bonjour, vous êtes bien chez DanielCraft, de Loïc Daniel, "
            "merci de laisser un message."
        )
    )
    voicemail_max_duration: int = Field(default=60)  # secondes (durée max enregistrement)
    voicemail_silence_timeout_sec: int = Field(default=5)  # coupe si silence prolongé après la parole
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignorer les champs supplémentaires au lieu de les rejeter
    
    def __init__(self, config_path: Optional[Path] = None, **kwargs):
        """Initialise la configuration. Le .env est chargé depuis la racine du projet (base_path)."""
        base = _default_base_path()
        requested_env = os.environ.get("VG_ENV", kwargs.get("vg_env", "dev")).strip().lower()
        # Priorité: .env.<env> (ex: .env.prod), sinon fallback sur .env
        candidate_files = [base / f".env.{requested_env}", base / ".env"]
        for env_file in candidate_files:
            if env_file.exists():
                kwargs.setdefault("_env_file", str(env_file))
                break
        super().__init__(**kwargs)

        if config_path:
            self.config_path = Path(config_path)
        elif not self.config_path:
            for candidate in (self.base_path / "config" / "config.yaml", self.base_path / "config.yaml"):
                if candidate.exists():
                    self.config_path = candidate
                    break
            if not self.config_path:
                self.config_path = self.base_path / "config.yaml"

        if self.config_path and self.config_path.exists():
            self.load_from_yaml(self.config_path)

        # Priorité .env / variables d'environnement sur le YAML pour la voix
        self._apply_env_overrides()
        # Mode UI (répondeur / téléphone) persisté dans data/incoming_line_mode.yaml
        try:
            from backend.core.incoming_line_mode import load_incoming_line_mode

            load_incoming_line_mode(self)
        except Exception:
            pass
    def _apply_env_overrides(self) -> None:
        """Réapplique les variables d'environnement (.env) pour que .env prime sur le YAML."""
        # Runtime/prod-critical overrides (DB, queue, API) to avoid YAML forcing SQLite in production.
        if os.environ.get("DATABASE_URL"):
            self.database_url = os.environ.get("DATABASE_URL", "").strip()
        if os.environ.get("CELERY_BROKER_URL"):
            self.celery_broker_url = os.environ.get("CELERY_BROKER_URL", "").strip() or None
        if os.environ.get("CELERY_RESULT_BACKEND"):
            self.celery_result_backend = os.environ.get("CELERY_RESULT_BACKEND", "").strip() or None
        if os.environ.get("API_HOST"):
            self.api_host = os.environ.get("API_HOST", "").strip() or self.api_host
        if os.environ.get("API_PORT"):
            try:
                self.api_port = int(os.environ.get("API_PORT", "").strip())
            except ValueError:
                pass
        if os.environ.get("API_DEBUG"):
            self.api_debug = os.environ.get("API_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
        if os.environ.get("API_PUBLIC_ADMIN_TOKEN"):
            self.api_public_admin_token = os.environ.get("API_PUBLIC_ADMIN_TOKEN", "").strip() or None
        if os.environ.get("VG_UI_PASSWORD"):
            self.ui_password = os.environ.get("VG_UI_PASSWORD", "").strip() or None
        if os.environ.get("VG_UI_SESSION_SECRET"):
            self.ui_session_secret = os.environ.get("VG_UI_SESSION_SECRET", "").strip() or None
        if os.environ.get("PUBLIC_BASE_URL"):
            self.public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip() or self.public_base_url
        if os.environ.get("AGENDA_PUBLIC_SECRET"):
            self.agenda_public_secret = os.environ.get("AGENDA_PUBLIC_SECRET", "").strip() or self.agenda_public_secret

        if os.environ.get("VOICE_RECOGNITION_ENGINE"):
            self.voice_recognition_engine = os.environ.get("VOICE_RECOGNITION_ENGINE", "").strip().lower()
        if os.environ.get("VOICE_SYNTHESIS_ENGINE"):
            self.voice_synthesis_engine = os.environ.get("VOICE_SYNTHESIS_ENGINE", "").strip().lower()
        if os.environ.get("VOSK_MODEL_PATH"):
            self.vosk_model_path = os.environ.get("VOSK_MODEL_PATH", "").strip() or None
        if os.environ.get("STT_SERVICE_URL"):
            self.stt_service_url = os.environ.get("STT_SERVICE_URL", "").strip().rstrip("/") or None
        if os.environ.get("STT_INTERNAL_TOKEN"):
            self.stt_internal_token = os.environ.get("STT_INTERNAL_TOKEN", "").strip() or None
        if os.environ.get("TTS_SERVICE_URL"):
            self.tts_service_url = os.environ.get("TTS_SERVICE_URL", "").strip().rstrip("/") or None
        if os.environ.get("ELEVENLABS_API_KEY"):
            self.elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip() or None
        if os.environ.get("ELEVENLABS_VOICE_ID"):
            self.elevenlabs_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip() or None
        if os.environ.get("ELEVENLABS_MODEL_ID"):
            mid = os.environ.get("ELEVENLABS_MODEL_ID", "").strip()
            if mid:
                self.elevenlabs_model_id = mid
        if os.environ.get("VOICEMAIL_MODE"):
            mode = os.environ.get("VOICEMAIL_MODE", "").strip().lower()
            if mode in ("simple", "ivr", "conversation"):
                self.voicemail_mode = mode
        if os.environ.get("OSINT_SERVICE_URL"):
            self.osint_service_url = os.environ.get("OSINT_SERVICE_URL", "").strip().rstrip("/") or None
        if os.environ.get("OSINT_INTERNAL_TOKEN"):
            self.osint_internal_token = os.environ.get("OSINT_INTERNAL_TOKEN", "").strip() or None
        if os.environ.get("MODEM_PORT"):
            self.modem_port = os.environ.get("MODEM_PORT", "").strip() or None
        if os.environ.get("USE_TELEPHONY_DAEMON"):
            self.use_telephony_daemon = os.environ.get("USE_TELEPHONY_DAEMON", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        if os.environ.get("TELEPHONY_DAEMON_URL"):
            self.telephony_daemon_url = os.environ.get("TELEPHONY_DAEMON_URL", "").strip().rstrip("/")
        if os.environ.get("TELEPHONY_PUBLIC_API_URL"):
            self.telephony_public_api_url = os.environ.get("TELEPHONY_PUBLIC_API_URL", "").strip().rstrip("/")
        if os.environ.get("TELEPHONY_INTERNAL_TOKEN"):
            self.telephony_internal_token = os.environ.get("TELEPHONY_INTERNAL_TOKEN", "").strip() or None
        if os.environ.get("TELEPHONY_BIND_HOST"):
            h = os.environ.get("TELEPHONY_BIND_HOST", "").strip()
            if h:
                self.telephony_bind_host = h
        if os.environ.get("TELEPHONY_BIND_PORT"):
            try:
                self.telephony_bind_port = int(os.environ.get("TELEPHONY_BIND_PORT", "").strip())
            except ValueError:
                pass
        if os.environ.get("MODEM_BAUDRATE"):
            try:
                self.modem_baudrate = int(os.environ.get("MODEM_BAUDRATE", "").strip())
            except ValueError:
                pass
        if os.environ.get("MODEM_VOICE_VSM"):
            self.modem_voice_vsm = os.environ.get("MODEM_VOICE_VSM", "").strip() or None
        if os.environ.get("CID_WAIT_SEC"):
            try:
                self.cid_wait_sec = float(os.environ.get("CID_WAIT_SEC", "").strip())
            except ValueError:
                pass
        if os.environ.get("RINGS_BEFORE_ANSWER"):
            try:
                self.rings_before_answer = int(os.environ.get("RINGS_BEFORE_ANSWER", "").strip())
            except ValueError:
                pass
        if os.environ.get("INCOMING_AUTO_ANSWER"):
            self.incoming_auto_answer = os.environ.get("INCOMING_AUTO_ANSWER", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        if os.environ.get("MODEM_COUNTRY_GCI"):
            self.modem_country_gci = os.environ.get("MODEM_COUNTRY_GCI", "").strip() or None
        if os.environ.get("MODEM_VOICE_VGR"):
            try:
                self.modem_voice_vgr = int(os.environ.get("MODEM_VOICE_VGR", "").strip())
            except ValueError:
                pass
        if os.environ.get("MODEM_VOICE_VGT"):
            try:
                self.modem_voice_vgt = int(os.environ.get("MODEM_VOICE_VGT", "").strip())
            except ValueError:
                pass
        if os.environ.get("WHITELIST_RING_ONLY"):
            self.whitelist_ring_only = os.environ.get("WHITELIST_RING_ONLY", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        if os.environ.get("OUTGOING_USE_VTR"):
            self.outgoing_use_vtr = os.environ.get("OUTGOING_USE_VTR", "").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        if os.environ.get("TELEPHONY_BACKEND"):
            self.telephony_backend = os.environ.get("TELEPHONY_BACKEND", "").strip().lower() or "modem"
        if os.environ.get("SIP_URI"):
            self.sip_uri = os.environ.get("SIP_URI", "").strip() or None
        if os.environ.get("SIP_USER"):
            self.sip_user = os.environ.get("SIP_USER", "").strip() or None
        if os.environ.get("SIP_PASSWORD"):
            self.sip_password = os.environ.get("SIP_PASSWORD", "").strip() or None
        if os.environ.get("SIP_REALM"):
            self.sip_realm = os.environ.get("SIP_REALM", "").strip() or None

    def load_from_yaml(self, path: Path):
        """
        Charge la configuration depuis un fichier YAML
        
        Args:
            path: Chemin vers le fichier YAML
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    for key, value in yaml_config.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
                        else:
                            # Stocker les clés non reconnues comme attributs dynamiques
                            setattr(self, key, value)
        except Exception as e:
            print(f"Erreur lors du chargement de la config YAML: {e}")
    
    def save_to_yaml(self, path: Optional[Path] = None):
        """Sauvegarde la configuration dans un fichier YAML"""
        if not path:
            path = self.config_path or self.base_path / "config.yaml"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        config_dict = {
            "database_url": self.database_url,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "modem_port": self.modem_port,
            "voice_recognition_engine": self.voice_recognition_engine,
            "voice_synthesis_engine": self.voice_synthesis_engine,
            "voice_language": self.voice_language,
            "edge_tts_voice": getattr(self, "edge_tts_voice", None),
            "whisper_model": self.whisper_model,
            "rings_before_answer": self.rings_before_answer,
            "incoming_auto_answer": self.incoming_auto_answer,
            "block_enabled": self.block_enabled,
            "voicemail_enabled": self.voicemail_enabled,
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)

