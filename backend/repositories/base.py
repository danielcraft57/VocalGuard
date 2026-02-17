"""
Repository de base avec méthodes communes
"""

from typing import Generic, TypeVar, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from loguru import logger

from backend.database.models import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Repository de base avec méthodes CRUD communes"""
    
    def __init__(self, model: type[ModelType], db: Session):
        """
        Initialise le repository
        
        Args:
            model: Classe du modèle SQLAlchemy
            db: Session de base de données
        """
        self.model = model
        self.db = db
    
    def create(self, **kwargs) -> ModelType:
        """
        Crée une nouvelle entité
        
        Args:
            **kwargs: Attributs de l'entité
            
        Returns:
            Entité créée
        """
        entity = self.model(**kwargs)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        logger.debug(f"Entité créée: {self.model.__name__} (id={entity.id})")
        return entity
    
    def get_by_id(self, entity_id: int) -> Optional[ModelType]:
        """
        Récupère une entité par son ID
        
        Args:
            entity_id: ID de l'entité
            
        Returns:
            Entité ou None si non trouvée
        """
        return self.db.query(self.model).filter(self.model.id == entity_id).first()
    
    def get_all(self, skip: int = 0, limit: int = 100, **filters) -> List[ModelType]:
        """
        Récupère toutes les entités avec filtres optionnels
        
        Args:
            skip: Nombre d'entités à sauter
            limit: Nombre maximum d'entités à retourner
            **filters: Filtres à appliquer
            
        Returns:
            Liste des entités
        """
        query = self.db.query(self.model)
        
        # Appliquer les filtres
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.filter(getattr(self.model, key) == value)
        
        return query.offset(skip).limit(limit).all()
    
    def count(self, **filters) -> int:
        """
        Compte les entités avec filtres optionnels
        
        Args:
            **filters: Filtres à appliquer
            
        Returns:
            Nombre d'entités
        """
        query = self.db.query(self.model)
        
        for key, value in filters.items():
            if hasattr(self.model, key) and value is not None:
                query = query.filter(getattr(self.model, key) == value)
        
        return query.count()
    
    def update(self, entity_id: int, **kwargs) -> Optional[ModelType]:
        """
        Met à jour une entité
        
        Args:
            entity_id: ID de l'entité
            **kwargs: Attributs à mettre à jour
            
        Returns:
            Entité mise à jour ou None si non trouvée
        """
        entity = self.get_by_id(entity_id)
        if not entity:
            return None
        
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        self.db.commit()
        self.db.refresh(entity)
        logger.debug(f"Entité mise à jour: {self.model.__name__} (id={entity_id})")
        return entity
    
    def delete(self, entity_id: int) -> bool:
        """
        Supprime une entité
        
        Args:
            entity_id: ID de l'entité
            
        Returns:
            True si supprimée, False si non trouvée
        """
        entity = self.get_by_id(entity_id)
        if not entity:
            return False
        
        self.db.delete(entity)
        self.db.commit()
        logger.debug(f"Entité supprimée: {self.model.__name__} (id={entity_id})")
        return True
    
    def find_by(self, **criteria) -> List[ModelType]:
        """
        Trouve des entités selon des critères
        
        Args:
            **criteria: Critères de recherche
            
        Returns:
            Liste des entités correspondantes
        """
        query = self.db.query(self.model)
        
        filters = []
        for key, value in criteria.items():
            if hasattr(self.model, key):
                filters.append(getattr(self.model, key) == value)
        
        if filters:
            query = query.filter(and_(*filters))
        
        return query.all()
    
    def find_one_by(self, **criteria) -> Optional[ModelType]:
        """
        Trouve une entité selon des critères
        
        Args:
            **criteria: Critères de recherche
            
        Returns:
            Entité ou None si non trouvée
        """
        results = self.find_by(**criteria)
        return results[0] if results else None

