"""
Repository pour les appelants
"""

from typing import List, Optional
from sqlalchemy.orm import Session

from backend.repositories.base import BaseRepository
from backend.database.models import Caller


class CallerRepository(BaseRepository[Caller]):
    """Repository pour la gestion des appelants"""
    
    def __init__(self, db: Session):
        """Initialise le repository des appelants"""
        super().__init__(Caller, db)
    
    def get_by_phone_number(self, phone_number: str) -> Optional[Caller]:
        """
        Récupère un appelant par son numéro de téléphone
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Appelant ou None si non trouvé
        """
        return self.find_one_by(phone_number=phone_number)
    
    def get_blocked_callers(self) -> List[Caller]:
        """
        Récupère tous les appelants bloqués
        
        Returns:
            Liste des appelants bloqués
        """
        return self.find_by(is_blocked=True)
    
    def get_whitelisted_callers(self) -> List[Caller]:
        """
        Récupère tous les appelants en liste blanche
        
        Returns:
            Liste des appelants en liste blanche
        """
        return self.find_by(is_whitelisted=True)
    
    def block_caller(self, phone_number: str) -> Optional[Caller]:
        """
        Bloque un appelant
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Appelant bloqué ou None si non trouvé
        """
        caller = self.get_by_phone_number(phone_number)
        if caller:
            return self.update(caller.id, is_blocked=True)
        return None
    
    def whitelist_caller(self, phone_number: str) -> Optional[Caller]:
        """
        Ajoute un appelant à la liste blanche
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Appelant en liste blanche ou None si non trouvé
        """
        caller = self.get_by_phone_number(phone_number)
        if caller:
            return self.update(caller.id, is_whitelisted=True)
        return None
    
    def create_or_update(
        self,
        phone_number: str,
        name: Optional[str] = None,
        is_blocked: bool = False,
        is_whitelisted: bool = False,
        **kwargs
    ) -> Caller:
        """
        Crée ou met à jour un appelant
        
        Args:
            phone_number: Numéro de téléphone
            name: Nom de l'appelant
            is_blocked: Si l'appelant est bloqué
            is_whitelisted: Si l'appelant est en liste blanche
            **kwargs: Autres attributs
            
        Returns:
            Appelant créé ou mis à jour
        """
        caller = self.get_by_phone_number(phone_number)
        
        if caller:
            # Mettre à jour
            update_data = {
                "name": name or caller.name,
                "is_blocked": is_blocked,
                "is_whitelisted": is_whitelisted,
                **kwargs
            }
            return self.update(caller.id, **update_data)
        else:
            # Créer
            return self.create(
                phone_number=phone_number,
                name=name,
                is_blocked=is_blocked,
                is_whitelisted=is_whitelisted,
                **kwargs
            )

