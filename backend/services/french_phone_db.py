"""
Gestionnaire de base de données pour les numéros français
Utilise SQLite pour stocker les données de référence
"""

from pathlib import Path
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from loguru import logger

from backend.database.models import FrenchPhonePrefix
from backend.database.database import SessionLocal


class FrenchPhoneDatabase:
    """
    Gère la base de données des préfixes français
    """
    
    def __init__(self, db: Optional[Session] = None):
        """
        Initialise le gestionnaire de base de données
        
        Args:
            db: Session de base de données (optionnel)
        """
        self.db = db
    
    def get_session(self) -> Optional[Session]:
        """Obtient une session de base de données, ou None si la DB n'est pas initialisee."""
        if self.db:
            return self.db
        if SessionLocal is None:
            return None
        return SessionLocal()

    def get_prefix_info(self, prefix: str) -> Optional[Dict]:
        """
        Obtient les informations pour un préfixe depuis la base de données

        Args:
            prefix: Préfixe (ex: 0387)

        Returns:
            Dictionnaire avec les informations ou None
        """
        session = self.get_session()
        if session is None:
            return None
        try:
            prefix_obj = session.query(FrenchPhonePrefix).filter(
                FrenchPhonePrefix.prefix == prefix
            ).first()

            if prefix_obj:
                return {
                    "prefix": prefix_obj.prefix,
                    "city": prefix_obj.city,
                    "region": prefix_obj.region,
                    "department": prefix_obj.department,
                    "postal_code": prefix_obj.postal_code,
                    "operator": prefix_obj.operator,
                    "operator_type": prefix_obj.operator_type,
                    "line_type": prefix_obj.line_type,
                    "latitude": prefix_obj.latitude,
                    "longitude": prefix_obj.longitude,
                    "population": prefix_obj.population,
                }
        except Exception as e:
            logger.error(f"Erreur lors de la recherche du préfixe {prefix}: {e}")
        finally:
            if not self.db:
                session.close()

        return None
    
    def add_prefix(self, prefix_data: Dict) -> bool:
        """
        Ajoute ou met à jour un préfixe dans la base de données

        Args:
            prefix_data: Dictionnaire avec les données du préfixe

        Returns:
            True si l'opération réussit
        """
        session = self.get_session()
        if session is None:
            return False
        try:
            prefix = prefix_data.get('prefix')
            if not prefix:
                return False
            
            # Chercher si le préfixe existe déjà
            prefix_obj = session.query(FrenchPhonePrefix).filter(
                FrenchPhonePrefix.prefix == prefix
            ).first()
            
            if prefix_obj:
                # Mettre à jour
                for key, value in prefix_data.items():
                    if hasattr(prefix_obj, key) and value is not None:
                        setattr(prefix_obj, key, value)
            else:
                # Créer
                prefix_obj = FrenchPhonePrefix(**prefix_data)
                session.add(prefix_obj)
            
            session.commit()
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'ajout du préfixe: {e}")
            session.rollback()
            return False
        finally:
            if not self.db:
                session.close()
    
    def bulk_import(self, prefixes_data: List[Dict]) -> int:
        """
        Importe plusieurs préfixes en une fois
        
        Args:
            prefixes_data: Liste de dictionnaires avec les données
            
        Returns:
            Nombre de préfixes importés
        """
        session = self.get_session()
        if session is None:
            return 0
        count = 0
        try:
            for prefix_data in prefixes_data:
                prefix = prefix_data.get('prefix')
                if not prefix:
                    continue
                
                # Chercher si existe
                existing = session.query(FrenchPhonePrefix).filter(
                    FrenchPhonePrefix.prefix == prefix
                ).first()
                
                if existing:
                    # Mettre à jour
                    for key, value in prefix_data.items():
                        if hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                else:
                    # Créer
                    prefix_obj = FrenchPhonePrefix(**prefix_data)
                    session.add(prefix_obj)
                
                count += 1
                
                # Commit par batch de 100
                if count % 100 == 0:
                    session.commit()
            
            session.commit()
            logger.info(f"Importé {count} préfixes dans la base de données")
            return count
        except Exception as e:
            logger.error(f"Erreur lors de l'import en masse: {e}")
            session.rollback()
            return 0
        finally:
            if not self.db:
                session.close()
    
    def search_by_city(self, city: str) -> List[Dict]:
        """
        Recherche les préfixes par ville

        Args:
            city: Nom de la ville

        Returns:
            Liste de dictionnaires avec les préfixes
        """
        session = self.get_session()
        if session is None:
            return []
        try:
            prefixes = session.query(FrenchPhonePrefix).filter(
                FrenchPhonePrefix.city.ilike(f"%{city}%")
            ).all()
            
            return [{
                'prefix': p.prefix,
                'city': p.city,
                'region': p.region,
                'operator': p.operator,
            } for p in prefixes]
        except Exception as e:
            logger.error(f"Erreur lors de la recherche par ville: {e}")
            return []
        finally:
            if not self.db:
                session.close()
    
    def search_by_operator(self, operator: str) -> List[Dict]:
        """
        Recherche les préfixes par opérateur

        Args:
            operator: Nom de l'opérateur

        Returns:
            Liste de dictionnaires avec les préfixes
        """
        session = self.get_session()
        if session is None:
            return []
        try:
            prefixes = session.query(FrenchPhonePrefix).filter(
                FrenchPhonePrefix.operator.ilike(f"%{operator}%")
            ).all()
            
            return [{
                'prefix': p.prefix,
                'city': p.city,
                'region': p.region,
                'operator': p.operator,
            } for p in prefixes]
        except Exception as e:
            logger.error(f"Erreur lors de la recherche par opérateur: {e}")
            return []
        finally:
            if not self.db:
                session.close()
    
    def get_statistics(self) -> Dict:
        """
        Obtient des statistiques sur la base de données

        Returns:
            Dictionnaire avec les statistiques
        """
        session = self.get_session()
        if session is None:
            return {}
        try:
            total = session.query(FrenchPhonePrefix).count()
            operators = session.query(FrenchPhonePrefix.operator).distinct().count()
            cities = session.query(FrenchPhonePrefix.city).distinct().count()
            regions = session.query(FrenchPhonePrefix.region).distinct().count()
            
            return {
                'total_prefixes': total,
                'unique_operators': operators,
                'unique_cities': cities,
                'unique_regions': regions,
            }
        except Exception as e:
            logger.error(f"Erreur lors du calcul des statistiques: {e}")
            return {}
        finally:
            if not self.db:
                session.close()

