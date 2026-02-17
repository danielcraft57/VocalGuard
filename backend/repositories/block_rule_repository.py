"""
Repository pour les règles de blocage
"""

from typing import List
from sqlalchemy.orm import Session

from backend.repositories.base import BaseRepository
from backend.database.models import BlockRule


class BlockRuleRepository(BaseRepository[BlockRule]):
    """Repository pour la gestion des règles de blocage"""
    
    def __init__(self, db: Session):
        """Initialise le repository des règles de blocage"""
        super().__init__(BlockRule, db)
    
    def get_active_rules(self) -> List[BlockRule]:
        """
        Récupère toutes les règles de blocage actives
        
        Returns:
            Liste des règles actives
        """
        return self.find_by(is_active=True)

