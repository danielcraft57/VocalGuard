"""
Service de blocage d'appels
"""

import re
from typing import Optional, List
from sqlalchemy.orm import Session
from loguru import logger

from backend.repositories.caller_repository import CallerRepository
from backend.repositories.block_rule_repository import BlockRuleRepository
from backend.services.osint_service import OSINTService
from backend.core.config import Config


class BlockService:
    """Service pour la gestion du blocage d'appels"""
    
    def __init__(self, config: Config, db: Session):
        """
        Initialise le service de blocage
        
        Args:
            config: Configuration de l'application
            db: Session de base de données
        """
        self.config = config
        self.caller_repo = CallerRepository(db)
        self.block_rule_repo = BlockRuleRepository(db)
        self.osint_service = OSINTService(config)
        self.db = db
    
    async def is_blocked(self, phone_number: Optional[str], caller_name: Optional[str] = None) -> bool:
        """
        Vérifie si un appelant doit être bloqué
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            
        Returns:
            True si l'appel doit être bloqué
        """
        if not self.config.block_enabled:
            return False
        
        if not phone_number:
            return False
        
        # Vérifier si l'appelant est en liste blanche
        caller = self.caller_repo.get_by_phone_number(phone_number)
        if caller and caller.is_whitelisted:
            logger.debug(f"Appelant en liste blanche: {phone_number}")
            return False
        
        # Vérifier si l'appelant est explicitement bloqué
        if caller and caller.is_blocked:
            logger.debug(f"Appelant bloqué: {phone_number}")
            return True
        
        # Vérifier les règles de blocage
        if await self._check_block_rules(phone_number, caller_name):
            return True
        
        # Vérifier via OSINT
        osint_result = await self.osint_service.check_reputation(phone_number, caller_name)
        if osint_result.get("recommendation") == "block":
            logger.info(f"Appel bloqué via OSINT: {phone_number}")
            return True
        
        # Vérifier si c'est un numéro commercial/télémarketeur
        if osint_result.get("is_telemarketer") or (osint_result.get("is_commercial") and osint_result.get("confidence", 0.0) > 0.8):
            logger.info(f"Appel commercial/télémarketeur détecté: {phone_number}")
            return True
        
        # Vérifier via les services externes (si configuré)
        if self.config.block_service:
            return await self._check_external_service(phone_number, caller_name)
        
        return False
    
    async def _check_block_rules(self, phone_number: str, caller_name: Optional[str]) -> bool:
        """
        Vérifie les règles de blocage configurées
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            
        Returns:
            True si une règle correspond
        """
        rules = self.block_rule_repo.get_active_rules()
        
        for rule in rules:
            if rule.pattern_type == "exact":
                if phone_number == rule.pattern:
                    logger.info(f"Appel bloqué par règle exacte: {rule.name}")
                    return True
            
            elif rule.pattern_type == "prefix":
                if phone_number.startswith(rule.pattern):
                    logger.info(f"Appel bloqué par règle de préfixe: {rule.name}")
                    return True
            
            elif rule.pattern_type == "regex":
                try:
                    if re.match(rule.pattern, phone_number):
                        logger.info(f"Appel bloqué par règle regex: {rule.name}")
                        return True
                except re.error as e:
                    logger.warning(f"Regex invalide dans la règle {rule.name}: {e}")
        
        return False
    
    async def _check_external_service(self, phone_number: str, caller_name: Optional[str]) -> bool:
        """
        Vérifie via un service externe de blocage
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            
        Returns:
            True si l'appel doit être bloqué
        """
        # TODO: Implémenter l'intégration avec les services externes
        # (Nomorobo, Truecaller, etc.)
        
        # Vérification basique par patterns suspects
        if phone_number.startswith('V') and len(phone_number) > 10:
            logger.info(f"Appel bloqué (pattern suspect): {phone_number}")
            return True
        
        return False
    
    async def block_caller(self, phone_number: str, reason: Optional[str] = None) -> bool:
        """
        Bloque un appelant
        
        Args:
            phone_number: Numéro de téléphone
            reason: Raison du blocage
            
        Returns:
            True si l'appelant a été bloqué
        """
        caller = self.caller_repo.create_or_update(
            phone_number=phone_number,
            is_blocked=True,
            is_whitelisted=False
        )
        
        logger.info(f"Appelant bloqué: {phone_number} ({reason})")
        return True
    
    async def whitelist_caller(self, phone_number: str) -> bool:
        """
        Ajoute un appelant à la liste blanche
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            True si l'appelant a été ajouté à la liste blanche
        """
        caller = self.caller_repo.create_or_update(
            phone_number=phone_number,
            is_blocked=False,
            is_whitelisted=True
        )
        
        logger.info(f"Appelant ajouté à la liste blanche: {phone_number}")
        return True

