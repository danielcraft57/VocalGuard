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

    def ensure_profiles_batch(
        self,
        phone_numbers: list[str],
        *,
        batch_size: int = 200,
    ) -> int:
        """
        Cree en lot les profils OSINT manquants (bulk_insert_mappings).

        @param phone_numbers Numeros a assurer.
        @param batch_size Taille des commits.
        @returns Nombre de profils nouvellement inseres.
        """
        if not phone_numbers:
            return 0
        normalized_map: dict[str, str] = {}
        for raw in phone_numbers:
            if not raw:
                continue
            norm = self._normalize_number(raw)
            if norm and norm not in normalized_map:
                normalized_map[norm] = raw

        existing = {
            row[0]
            for row in self._db.query(PhoneNumberProfile.normalized_number)
            .filter(PhoneNumberProfile.normalized_number.in_(list(normalized_map.keys())))
            .all()
        }
        to_insert = [
            {
                "phone_number": phone,
                "normalized_number": norm,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "is_company": False,
                "is_spam": False,
                "is_scam": False,
                "is_commercial": False,
                "is_telemarketer": False,
            }
            for norm, phone in normalized_map.items()
            if norm not in existing
        ]
        inserted = 0
        for i in range(0, len(to_insert), batch_size):
            chunk = to_insert[i : i + batch_size]
            if not chunk:
                continue
            self._db.bulk_insert_mappings(PhoneNumberProfile, chunk)
            self._db.commit()
            inserted += len(chunk)
        if inserted:
            logger.info("Profils OSINT crees en lot: {}", inserted)
        return inserted

    def force_queue_refresh(self, phone_number: str) -> PhoneNumberProfile:
        """
        Cree ou recupere le profil puis relance une tache Celery OSINT (file d'attente).

        @param phone_number Numero a rafraichir.
        @returns Profil associe.
        """
        profile = self.ensure_profile_for_number(
            phone_number=phone_number,
            max_age=timedelta(days=9999),
        )
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

