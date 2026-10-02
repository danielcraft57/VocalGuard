"""
Taches Celery pour l'enrichissement OSINT des numeros de telephone.

Ces taches tournent en arriere-plan et mettent a jour le modele
`PhoneNumberProfile` a partir du service `OSINTService` existant.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session
import httpx

from backend.celery_app import celery_app
from backend.core.config import Config
from backend.database import database as db_module
from backend.database.models import PhoneNumberProfile, EntreprisePhoneAnalysis
from backend.osint.persist import apply_osint_result_to_profile
from backend.services.osint_service import OSINTService

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


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

        apply_osint_result_to_profile(db, profile, result)
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

