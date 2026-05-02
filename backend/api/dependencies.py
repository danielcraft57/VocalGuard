"""
Dépendances FastAPI pour l'injection de dépendances
"""

import threading
from typing import Generator, Optional
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.database.database import get_db
from backend.repositories.call_repository import CallRepository
from backend.repositories.caller_repository import CallerRepository
from backend.repositories.voicemail_repository import VoicemailRepository
from backend.repositories.block_rule_repository import BlockRuleRepository
from backend.services.call_service import CallService
from backend.services.block_service import BlockService
from backend.core.config import Config

_config_singleton: Optional[Config] = None
_config_lock = threading.Lock()


def get_config() -> Config:
    """
    Configuration applicative (singleton).

    Évite de réinstancier Config() à chaque requête : pydantic-settings rouvre les fichiers
    .env à chaque construction et peut provoquer OSError « Too many open files » sous charge.
    """
    global _config_singleton
    if _config_singleton is None:
        with _config_lock:
            if _config_singleton is None:
                _config_singleton = Config()
    return _config_singleton


def reset_config_singleton() -> None:
    """Réinitialise le cache (tests uniquement)."""
    global _config_singleton
    with _config_lock:
        _config_singleton = None


def get_call_repository(db: Session = Depends(get_db)) -> CallRepository:
    """
    Obtient le repository des appels
    
    Args:
        db: Session de base de données
        
    Returns:
        Repository des appels
    """
    return CallRepository(db)


def get_caller_repository(db: Session = Depends(get_db)) -> CallerRepository:
    """
    Obtient le repository des appelants
    
    Args:
        db: Session de base de données
        
    Returns:
        Repository des appelants
    """
    return CallerRepository(db)


def get_voicemail_repository(db: Session = Depends(get_db)) -> VoicemailRepository:
    """
    Obtient le repository des messages vocaux
    
    Args:
        db: Session de base de données
        
    Returns:
        Repository des messages vocaux
    """
    return VoicemailRepository(db)


def get_call_service(db: Session = Depends(get_db)) -> CallService:
    """
    Obtient le service des appels
    
    Args:
        db: Session de base de données
        
    Returns:
        Service des appels
    """
    return CallService(db)


def get_block_service(
    config: Config = Depends(get_config),
    db: Session = Depends(get_db)
) -> BlockService:
    """
    Obtient le service de blocage
    
    Args:
        config: Configuration
        db: Session de base de données
        
    Returns:
        Service de blocage
    """
    return BlockService(config, db)


def get_block_rule_repository(db: Session = Depends(get_db)) -> BlockRuleRepository:
    """
    Obtient le repository des regles de blocage.
    """
    return BlockRuleRepository(db)

