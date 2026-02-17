"""
Repository pour les messages vocaux
"""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.repositories.base import BaseRepository
from backend.database.models import Voicemail


class VoicemailRepository(BaseRepository[Voicemail]):
    """Repository pour la gestion des messages vocaux"""
    
    def __init__(self, db: Session):
        """Initialise le repository des messages vocaux"""
        super().__init__(Voicemail, db)
    
    def get_unread(self, skip: int = 0, limit: int = 100) -> List[Voicemail]:
        """
        Récupère les messages vocaux non lus
        
        Args:
            skip: Nombre de messages à sauter
            limit: Nombre maximum de messages
            
        Returns:
            Liste des messages non lus
        """
        return self.get_all(skip=skip, limit=limit, is_read=False)
    
    def get_recent(self, limit: int = 50) -> List[Voicemail]:
        """
        Récupère les messages vocaux récents
        
        Args:
            limit: Nombre maximum de messages
            
        Returns:
            Liste des messages récents
        """
        return self.db.query(Voicemail).order_by(desc(Voicemail.created_at)).limit(limit).all()
    
    def mark_as_read(self, voicemail_id: int) -> Optional[Voicemail]:
        """
        Marque un message vocal comme lu
        
        Args:
            voicemail_id: ID du message vocal
            
        Returns:
            Message vocal mis à jour ou None si non trouvé
        """
        return self.update(voicemail_id, is_read=True)
    
    def archive(self, voicemail_id: int) -> Optional[Voicemail]:
        """
        Archive un message vocal
        
        Args:
            voicemail_id: ID du message vocal
            
        Returns:
            Message vocal archivé ou None si non trouvé
        """
        return self.update(voicemail_id, is_archived=True)
    
    def create_voicemail(
        self,
        audio_file: str,
        phone_number: Optional[str] = None,
        caller_id: Optional[int] = None,
        call_id: Optional[int] = None,
        transcription: Optional[str] = None,
        duration: Optional[int] = None
    ) -> Voicemail:
        """
        Crée un nouveau message vocal
        
        Args:
            audio_file: Chemin du fichier audio
            phone_number: Numéro de téléphone
            caller_id: ID de l'appelant
            call_id: ID de l'appel associé
            transcription: Transcription du message
            duration: Durée en secondes
            
        Returns:
            Message vocal créé
        """
        return self.create(
            audio_file=audio_file,
            phone_number=phone_number,
            caller_id=caller_id,
            call_id=call_id,
            transcription=transcription,
            duration=duration,
            is_read=False,
            is_archived=False
        )

