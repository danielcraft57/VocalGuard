"""
Configuration de VocalGuard
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml


class Config(BaseSettings):
    """Configuration de l'application"""
    
    # Chemins
    base_path: Path = Path.home() / ".vocalguard"
    config_path: Optional[Path] = None
    
    # Base de données
    database_url: str = Field(default="sqlite:///vocalguard.db")
    
    # Celery / taches asynchrones
    celery_broker_url: Optional[str] = Field(default=None)
    celery_result_backend: Optional[str] = Field(default=None)
    
    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=False)
    
    # Modem
    modem_port: Optional[str] = Field(default=None)  # Auto-détection si None
    modem_baudrate: int = Field(default=115200)
    
    # Voice
    voice_recognition_engine: str = Field(default="whisper")  # whisper ou vosk
    voice_synthesis_engine: str = Field(default="pyttsx3")  # pyttsx3 ou gtts
    voice_language: str = Field(default="fr")
    
    # Whisper
    whisper_model: str = Field(default="base")
    whisper_device: str = Field(default="cpu")  # cpu ou cuda
    
    # VOSK
    vosk_model_path: Optional[str] = Field(default=None)
    
    # Appels
    rings_before_answer: int = Field(default=2)
    max_call_duration: int = Field(default=300)  # secondes
    
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
    voicemail_max_duration: int = Field(default=120)  # secondes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignorer les champs supplémentaires au lieu de les rejeter
    
    def __init__(self, config_path: Optional[Path] = None, **kwargs):
        """Initialise la configuration"""
        super().__init__(**kwargs)
        
        if config_path:
            self.config_path = Path(config_path)
        elif not self.config_path:
            self.config_path = self.base_path / "config.yaml"
        
        # Charger la configuration depuis le fichier YAML si il existe
        if self.config_path and self.config_path.exists():
            self.load_from_yaml(self.config_path)
    
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
            "whisper_model": self.whisper_model,
            "rings_before_answer": self.rings_before_answer,
            "block_enabled": self.block_enabled,
            "voicemail_enabled": self.voicemail_enabled,
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)

