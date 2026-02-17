"""
Services OSINT de haut niveau pour le backend VocalGuard.

Ce module introduit `PhoneOsintService` qui fait le lien entre:
- les outils OSINT existants (`OSINTService` dans `backend.services.osint_service`),
- la base de donnees (modele `PhoneNumberProfile`),
- et l'orchestrateur de taches Celery.
"""

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.database.models import PhoneNumberProfile
from backend.services.osint_service import OSINTService

from backend.celery_app import celery_app


class PhoneOsintService:
    """
    Service d'enrichissement OSINT persistant pour les numeros de telephone.
    
    Il se charge de:
    - normaliser les numeros,
    - trouver ou creer un `PhoneNumberProfile`,
    - declencher si besoin une tache Celery d'enrichissement asynchrone.
    """

    def __init__(self, db: Session, config: Optional[Config] = None) -> None:
        """
        Initialise le service.
        
        Args:
            db: Session SQLAlchemy synchrone.
            config: Configuration applicative (optionnelle).
        """
        self._db = db
        self._config = config or Config()
        self._osint_service = OSINTService(self._config)

    def _normalize_number(self, phone_number: str) -> str:
        """
        Normalise un numero en utilisant la logique existante d'OSINTService.
        
        Args:
            phone_number: Numero a normaliser.
        
        Returns:
            Numero nettoye/normalise.
        """
        return self._osint_service._clean_phone_number(phone_number)  # type: ignore[attr-defined]

    def ensure_profile_for_number(
        self,
        phone_number: str,
        caller_id: Optional[int] = None,
        max_age: timedelta = timedelta(days=7),
    ) -> PhoneNumberProfile:
        """
        Retourne un profil OSINT pour le numero, en le creant si necessaire.
        
        Si le profil est trop ancien, une tache Celery d'enrichissement
        est planifiee en arriere-plan.
        
        Args:
            phone_number: Numero a analyser.
            caller_id: Identifiant d'appelant associe (optionnel).
            max_age: Duree maximale d'anciennete avant rafraichissement.
        
        Returns:
            Profil `PhoneNumberProfile` correspondant.
        """
        normalized = self._normalize_number(phone_number)

        profile = (
            self._db.query(PhoneNumberProfile)
            .filter(PhoneNumberProfile.normalized_number == normalized)
            .one_or_none()
        )

        if profile is None:
            profile = PhoneNumberProfile(
                phone_number=phone_number,
                normalized_number=normalized,
                caller_id=caller_id,
                created_at=datetime.utcnow(),
            )
            self._db.add(profile)
            self._db.commit()
            self._db.refresh(profile)
            logger.info(f"Profil OSINT cree pour le numero {phone_number} ({normalized})")

        # Mettre a jour le caller_id si nouvellement connu
        if caller_id and not profile.caller_id:
            profile.caller_id = caller_id
            self._db.commit()

        needs_refresh = (
            profile.last_checked_at is None
            or (datetime.utcnow() - profile.last_checked_at) > max_age
        )

        if needs_refresh:
            self._enqueue_refresh_task(profile_id=profile.id)

        return profile

    def _enqueue_refresh_task(self, profile_id: int) -> None:
        """
        Planifie une tache Celery pour rafraichir un profil.
        
        Args:
            profile_id: Identifiant du `PhoneNumberProfile` a rafraichir.
        """
        try:
            celery_app.send_task("backend.workers.osint_tasks.run_osint_for_profile", args=[profile_id])
            logger.debug(f"Tache OSINT planifiee pour le profil {profile_id}")
        except Exception as exc:
            logger.warning(f"Impossible de planifier la tache OSINT pour le profil {profile_id}: {exc}")

