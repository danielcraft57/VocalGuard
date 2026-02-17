"""
Repository pour les appels
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.repositories.base import BaseRepository
from backend.database.models import Call


class CallRepository(BaseRepository[Call]):
    """Repository pour la gestion des appels"""
    
    def __init__(self, db: Session):
        """Initialise le repository des appels"""
        super().__init__(Call, db)
    
    def get_recent_calls(self, limit: int = 50) -> List[Call]:
        """
        Récupère les appels récents
        
        Args:
            limit: Nombre maximum d'appels
            
        Returns:
            Liste des appels récents
        """
        return self.db.query(Call).order_by(desc(Call.call_time)).limit(limit).all()
    
    def get_by_status(self, status: str, skip: int = 0, limit: int = 100) -> List[Call]:
        """
        Récupère les appels par statut
        
        Args:
            status: Statut des appels
            skip: Nombre d'appels à sauter
            limit: Nombre maximum d'appels
            
        Returns:
            Liste des appels
        """
        return self.get_all(skip=skip, limit=limit, status=status)
    
    def get_by_phone_number(self, phone_number: str) -> List[Call]:
        """
        Récupère les appels d'un numéro de téléphone
        
        Args:
            phone_number: Numéro de téléphone
            
        Returns:
            Liste des appels
        """
        return self.find_by(phone_number=phone_number)
    
    def get_missed_calls(self, since: Optional[datetime] = None) -> List[Call]:
        """
        Récupère les appels manqués
        
        Args:
            since: Date à partir de laquelle chercher
            
        Returns:
            Liste des appels manqués
        """
        query = self.db.query(Call).filter(Call.status == "missed")
        
        if since:
            query = query.filter(Call.call_time >= since)
        
        return query.order_by(desc(Call.call_time)).all()
    
    def create_call(
        self,
        phone_number: Optional[str] = None,
        caller_name: Optional[str] = None,
        caller_id: Optional[int] = None,
        status: str = "ringing"
    ) -> Call:
        """
        Crée un nouvel appel
        
        Args:
            phone_number: Numéro de téléphone
            caller_name: Nom de l'appelant
            caller_id: ID de l'appelant dans la base
            status: Statut initial de l'appel
            
        Returns:
            Appel créé
        """
        return self.create(
            phone_number=phone_number,
            caller_name=caller_name,
            caller_id=caller_id,
            status=status,
            call_time=datetime.utcnow()
        )

