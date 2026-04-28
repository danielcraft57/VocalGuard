"""
Taches Celery pour l'enrichissement OSINT des numeros de telephone.

Ces taches tournent en arriere-plan et mettent a jour le modele
`PhoneNumberProfile` a partir du service `OSINTService` existant.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session
import httpx

from backend.celery_app import celery_app
from backend.core.config import Config
from backend.database import database as db_module
from backend.database.models import PhoneNumberProfile, EntreprisePhoneAnalysis
from backend.services.osint_service import OSINTService


_config = Config()
_db_initialised = False


def _ensure_db() -> Session:
    """
    S'assure que la base de donnees est initialisee et renvoie une session.
    
    Returns:
        Session SQLAlchemy synchrone.
    """
    global _db_initialised

    if not _db_initialised or db_module.SessionLocal is None:
        logger.info("Initialisation de la base de donnees pour les workers Celery")
        asyncio.run(db_module.init_database(_config.database_url))
        _db_initialised = True

    if db_module.SessionLocal is None:
        raise RuntimeError("SessionLocal non initialisee apres init_database")

    return db_module.SessionLocal()


def _apply_osint_result_to_profile(
    profile: PhoneNumberProfile,
    result: Dict[str, Any],
) -> None:
    """
    Recopie les champs utiles du resultat OSINT vers le profil.
    
    Args:
        profile: Profil a mettre a jour.
        result: Donnees OSINT brutes.
    """
    profile.country = result.get("country") or profile.country
    profile.region = result.get("region") or profile.region
    profile.city = result.get("city") or profile.city
    profile.department = result.get("department") or profile.department
    profile.postal_code = result.get("postal_code") or profile.postal_code
    profile.line_type = result.get("line_type") or profile.line_type
    profile.operator = result.get("operator") or profile.operator
    profile.carrier = result.get("carrier") or profile.carrier

    profile.name = result.get("name") or profile.name
    profile.company_name = result.get("company_name") or profile.company_name
    profile.is_company = bool(result.get("is_company") or profile.is_company)

    profile.reputation = result.get("reputation") or profile.reputation
    profile.is_spam = bool(result.get("is_spam") or profile.is_spam)
    profile.is_scam = bool(result.get("is_scam") or profile.is_scam)
    profile.is_commercial = bool(result.get("is_commercial") or profile.is_commercial)
    profile.is_telemarketer = bool(result.get("is_telemarketer") or profile.is_telemarketer)

    confidence: Optional[float] = result.get("confidence")
    if confidence is not None:
        # On stocke la confiance sur 0-100
        profile.confidence = int(confidence * 100)

    profile.raw_data = result
    profile.last_checked_at = datetime.utcnow()


@celery_app.task(name="backend.workers.osint_tasks.run_osint_for_profile")
def run_osint_for_profile(profile_id: int) -> None:
    """
    Tache Celery principale: enrichit un `PhoneNumberProfile` par OSINT.
    
    Args:
        profile_id: Identifiant du profil a analyser.
    """
    logger.info(f"Tache OSINT demarree pour le profil {profile_id}")

    db: Session = _ensure_db()
    try:
        profile: Optional[PhoneNumberProfile] = db.get(PhoneNumberProfile, profile_id)  # type: ignore[arg-type]
        if profile is None:
            logger.warning(f"Profil OSINT {profile_id} introuvable en base")
            return

        osint_service = OSINTService(_config)
        result = asyncio.run(osint_service.enrich_phone_number(profile.phone_number))

        if not isinstance(result, dict):
            logger.error(f"Resultat OSINT invalide pour le profil {profile_id}: {type(result)}")
            return

        _apply_osint_result_to_profile(profile, result)
        db.commit()
        logger.info(f"Profil OSINT {profile_id} mis a jour avec succes")

        # Marquer les analyses entreprise liées comme terminées
        try:
            db.query(EntreprisePhoneAnalysis).filter(EntreprisePhoneAnalysis.phone_profile_id == profile_id).filter(EntreprisePhoneAnalysis.status == "queued").update(  # type: ignore[attr-defined]
                {"status": "done", "updated_at": datetime.utcnow()},
                synchronize_session=False,
            )
            db.commit()
        except Exception as exc:
            logger.warning(f"Impossible de mettre à jour EntreprisePhoneAnalysis pour profile_id={profile_id}: {exc}")
            db.rollback()

        # Notifier le backend (WS) via endpoint HTTP
        try:
            host = (_config.api_host or "127.0.0.1").strip()
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            # Note: le routeur realtime n'est pas préfixé /api/v1 (WS: /ws/events).
            url = f"http://{host}:{int(_config.api_port)}/events/osint"
            httpx.post(
                url,
                json={"type": "osint.profile.completed", "data": {"profile_id": profile_id, "phone_number": profile.phone_number}},
                timeout=2.0,
            )
        except Exception as exc:
            logger.debug(f"Notification WS OSINT ignorée (backend indisponible): {exc}")

    except Exception as exc:
        logger.exception(f"Erreur dans la tache OSINT pour le profil {profile_id}: {exc}")
        db.rollback()
        try:
            host = (_config.api_host or "127.0.0.1").strip()
            if host in ("0.0.0.0", "::"):
                host = "127.0.0.1"
            url = f"http://{host}:{int(_config.api_port)}/events/osint"
            httpx.post(
                url,
                json={"type": "osint.profile.failed", "data": {"profile_id": profile_id, "error": str(exc)[:500]}},
                timeout=2.0,
            )
        except Exception:
            pass
    finally:
        db.close()

