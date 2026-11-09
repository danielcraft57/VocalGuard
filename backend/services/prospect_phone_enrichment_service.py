"""
Enrichissement OSINT + ProspectLab pour les prospects importes.
"""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from backend.core.config import Config
from backend.core.events import EventType
from backend.database.models import (
    PhoneNumberProfile,
    ProspectPhone,
    ProspectPhoneImportBatch,
)
from backend.osint.persist import apply_osint_result_to_profile
from backend.osint.services import PhoneOsintService
from backend.services.osint_service import OSINTService

_SPACE_RE = re.compile(r"\s+")


def _normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    s = unicodedata.normalize("NFKD", value.strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = _SPACE_RE.sub(" ", s)
    for token in ("sarl", "sas", "eurl", "sa", "sci", "snc"):
        s = re.sub(rf"\b{token}\b", " ", s)
    return _SPACE_RE.sub(" ", s).strip()


def compute_name_match_status(excel_name: str, *other_names: Optional[str]) -> str:
    """
    Compare le nom Excel aux noms OSINT / ProspectLab.

    @returns match | partial | mismatch | unknown
    """
    base = _normalize_name(excel_name)
    if not base:
        return "unknown"
    candidates = [_normalize_name(n) for n in other_names if _normalize_name(n)]
    if not candidates:
        return "unknown"
    for cand in candidates:
        if base == cand:
            return "match"
        if base in cand or cand in base:
            return "partial"
        base_tokens = set(base.split())
        cand_tokens = set(cand.split())
        if base_tokens and cand_tokens:
            overlap = len(base_tokens & cand_tokens) / max(len(base_tokens), len(cand_tokens))
            if overlap >= 0.6:
                return "partial"
    return "mismatch"


def _extract_prospectlab_id(result: Dict[str, Any]) -> Optional[int]:
    raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
    pl = raw.get("prospectlab") if isinstance(raw.get("prospectlab"), dict) else {}
    pl_id = pl.get("prospectlab_id")
    if pl_id is None:
        return None
    try:
        return int(pl_id)
    except (TypeError, ValueError):
        return None


def prospect_row_event_dict(prospect: ProspectPhone) -> Dict[str, Any]:
    """
    Snapshot leger d'un prospect pour les evenements WebSocket.

    @param prospect Ligne ORM.
    @returns Champs utiles a l'UI (fusion cote client).
    """
    return {
        "id": prospect.id,
        "name": prospect.name,
        "phone_number": prospect.phone_number,
        "import_batch_id": prospect.import_batch_id,
        "osint_status": prospect.osint_status,
        "prospectlab_status": prospect.prospectlab_status,
        "prospectlab_name": prospect.prospectlab_name,
        "prospectlab_entreprise_id": prospect.prospectlab_entreprise_id,
        "osint_company_name": prospect.osint_company_name,
        "osint_operator": prospect.osint_operator,
        "osint_region": prospect.osint_region,
        "osint_reputation": prospect.osint_reputation,
        "name_match_status": prospect.name_match_status,
        "enriched_at": prospect.enriched_at.isoformat() if prospect.enriched_at else None,
    }


def enrich_engine_label(config: Config) -> str:
    """Libelle moteur OSINT (node15, distant, local)."""
    url = (
        getattr(config, "osint_service_url", None)
        or (os.getenv("OSINT_SERVICE_URL") or "").strip()
    ).rstrip("/")
    if not url:
        return "local"
    host = (urlparse(url).hostname or "").lower()
    if "node15" in host:
        return "node15"
    return "osint-distant"


def default_enrich_parallel(config: Config) -> int:
    """
    Nombre de requetes OSINT paralleles (sync sans Celery).

    Defaut 2 si OSINT_SERVICE_URL (ex. node15), sinon 1.
    """
    raw = (os.getenv("PROSPECT_PHONE_ENRICH_PARALLEL") or "").strip()
    if raw.isdigit():
        return max(1, min(16, int(raw)))
    url = (
        getattr(config, "osint_service_url", None)
        or (os.getenv("OSINT_SERVICE_URL") or "").strip()
    )
    return 2 if url else 1


def notify_prospect_phone_realtime(config: Config, event_type: str, data: Dict[str, Any]) -> None:
    """
    Pousse un evenement vers l'API (worker Celery / process separe).

    @param config Config API (host/port).
    @param event_type Valeur EventType (str).
    @param data Payload data.
    """
    try:
        host = (config.api_host or "127.0.0.1").strip()
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        port = int(config.api_port)
        httpx.post(
            f"http://{host}:{port}/events/prospect-phone",
            json={"type": event_type, "data": data, "source": "ProspectPhoneEnrich"},
            timeout=2.0,
        )
    except Exception as exc:
        logger.debug("Notification enrich prospect ignoree: {}", exc)


def _thread_enrich_one(prospect_id: int, config: Config) -> tuple[int, str, Optional[Dict[str, Any]], Optional[str]]:
    """
    Enrichit un prospect dans un thread (session SQLAlchemy dediee).

    @returns (prospect_id, done|failed, dict prospect ou None, message erreur).
    """
    from backend.database import database as db_module

    session_factory = db_module.SessionLocal
    if session_factory is None:
        return prospect_id, "failed", None, "Base non initialisee"
    db = session_factory()
    try:
        svc = ProspectPhoneEnrichmentService(db, config)
        prospect = db.get(ProspectPhone, prospect_id)
        if prospect is None:
            return prospect_id, "failed", None, "Prospect introuvable"
        svc._enrich_one(prospect, use_celery=False)
        db.commit()
        db.refresh(prospect)
        return prospect_id, "done", prospect_row_event_dict(prospect), None
    except Exception as exc:
        db.rollback()
        try:
            prospect = db.get(ProspectPhone, prospect_id)
            if prospect is not None:
                prospect.osint_status = "failed"
                db.commit()
                db.refresh(prospect)
                return prospect_id, "failed", prospect_row_event_dict(prospect), str(exc)[:300]
        except Exception:
            db.rollback()
        return prospect_id, "failed", None, str(exc)[:300]
    finally:
        db.close()


def apply_osint_result_to_prospect(
    prospect: ProspectPhone,
    profile: PhoneNumberProfile,
    result: Dict[str, Any],
) -> None:
    """
    Recopie les champs utiles vers prospect_phones apres enrichissement OSINT.

    @param prospect Ligne prospect.
    @param profile Profil OSINT persiste.
    @param result Dict brut enrichissement.
    """
    prospect.phone_profile_id = profile.id
    prospect.osint_status = "done"
    prospect.osint_company_name = profile.company_name or profile.name
    prospect.osint_reputation = profile.reputation
    prospect.osint_operator = profile.operator or profile.carrier
    prospect.osint_region = profile.region or profile.city

    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    pl_id = _extract_prospectlab_id(result)
    if pl_id is not None or "prospectlab" in [str(s).lower() for s in sources]:
        prospect.prospectlab_status = "matched" if pl_id or profile.company_name else "not_found"
        prospect.prospectlab_entreprise_id = pl_id
        prospect.prospectlab_name = profile.company_name or profile.name
    elif prospect.prospectlab_status == "pending":
        prospect.prospectlab_status = "not_found"

    prospect.name_match_status = compute_name_match_status(
        prospect.name,
        prospect.prospectlab_name,
        prospect.osint_company_name,
    )
    prospect.enriched_at = datetime.utcnow()


class ProspectPhoneEnrichmentService:
    """Orchestre l'enrichissement d'un lot importe."""

    def __init__(self, db: Session, config: Optional[Config] = None) -> None:
        self._db = db
        self._config = config or Config()
        self._phone_osint = PhoneOsintService(db, self._config)
        self._osint = OSINTService(self._config)

    @staticmethod
    def celery_available() -> bool:
        """Indique si un worker Celery repond (sinon enrichissement synchrone)."""
        try:
            from backend.celery_app import celery_app

            ping = celery_app.control.ping(timeout=1.0)
            return bool(ping)
        except Exception:
            return False

    def enrich_batch(
        self,
        batch_id: int,
        *,
        use_celery: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        Lance l'enrichissement pour tous les prospects du lot.

        @param batch_id Identifiant batch import.
        @param use_celery Si True, tente Celery puis repli synchrone.
        @param progress_callback Heartbeat (batch_id, enrich_done, ...).
        """
        batch = self._db.get(ProspectPhoneImportBatch, batch_id)
        if batch is None:
            raise ValueError(f"Batch introuvable: {batch_id}")

        if use_celery and not self.celery_available():
            logger.info("Celery indisponible: enrichissement OSINT synchrone pour batch {}", batch_id)
            use_celery = False

        rows: List[ProspectPhone] = (
            self._db.query(ProspectPhone)
            .filter(ProspectPhone.import_batch_id == batch_id)
            .order_by(ProspectPhone.id.asc())
            .all()
        )
        batch.phase = "enrich"
        batch.enrich_total = len(rows)
        batch.enrich_done = 0
        batch.enrich_failed = 0
        batch.enrich_queued = 0
        batch.last_error = None
        self._db.commit()

        engine = enrich_engine_label(self._config)
        parallel = default_enrich_parallel(self._config) if not use_celery else 1
        queued_async = 0

        def emit(
            step: str,
            prospect: Optional[ProspectPhone],
            current: int,
            *,
            prospect_row: Optional[Dict[str, Any]] = None,
            error: Optional[str] = None,
        ) -> None:
            if not progress_callback:
                return
            payload: Dict[str, Any] = {
                "batch_id": batch_id,
                "phase": batch.phase,
                "step": step,
                "current": current,
                "enrich_total": batch.enrich_total,
                "enrich_done": batch.enrich_done,
                "enrich_failed": batch.enrich_failed,
                "enrich_queued": batch.enrich_queued,
                "enrich_engine": engine,
                "enrich_parallel": parallel,
            }
            if prospect_row is not None:
                payload["prospect"] = prospect_row
            elif prospect is not None:
                payload["prospect"] = prospect_row_event_dict(prospect)
            if error:
                payload["error"] = error
            try:
                progress_callback(payload)
            except Exception:
                pass

        if not use_celery and parallel > 1 and len(rows) > 1:
            logger.info(
                "Enrichissement batch {} en parallele x{} via {}",
                batch_id,
                parallel,
                engine,
            )
            processed = 0
            emit("parallel", None, 0)
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = {
                    pool.submit(_thread_enrich_one, prospect.id, self._config): prospect
                    for prospect in rows
                }
                for fut in as_completed(futures):
                    prospect = futures[fut]
                    processed += 1
                    try:
                        _pid, status, row_dict, err = fut.result()
                        if status == "done":
                            batch.enrich_done += 1
                        else:
                            batch.enrich_failed += 1
                            if err:
                                batch.last_error = err
                        self._db.commit()
                        emit(status, prospect, processed, prospect_row=row_dict, error=err)
                    except Exception as exc:
                        batch.enrich_failed += 1
                        batch.last_error = str(exc)[:500]
                        prospect.osint_status = "failed"
                        self._db.commit()
                        emit("failed", prospect, processed, error=str(exc)[:300])
        else:
            for idx, prospect in enumerate(rows, start=1):
                emit("start", prospect, idx)
                try:
                    if self._enrich_one(prospect, use_celery=use_celery):
                        batch.enrich_queued += 1
                        queued_async += 1
                        emit("queued", prospect, idx)
                    else:
                        batch.enrich_done += 1
                        emit("done", prospect, idx)
                except Exception as exc:
                    logger.warning("Enrichissement prospect_id={} echoue: {}", prospect.id, exc)
                    prospect.osint_status = "failed"
                    batch.enrich_failed += 1
                    batch.last_error = str(exc)[:500]
                    emit("failed", prospect, idx, error=str(exc)[:300])
                if idx % 10 == 0:
                    self._db.commit()
                elif not use_celery:
                    self._db.commit()

        if queued_async > 0 and batch.enrich_done + batch.enrich_failed < batch.enrich_total:
            batch.phase = "enrich"
        else:
            batch.phase = "done"
        self._db.commit()

    def _enrich_one(self, prospect: ProspectPhone, *, use_celery: bool) -> bool:
        """
        Enrichit un prospect.

        @returns True si file Celery (async), False si traite synchronement.
        """
        phone = (prospect.phone_number or "").strip()
        if not phone:
            prospect.osint_status = "skipped"
            prospect.prospectlab_status = "skipped"
            return False

        profile = self._phone_osint.force_queue_refresh(phone) if use_celery else self._phone_osint.ensure_profile_for_number(
            phone, max_age=timedelta(days=0)
        )
        prospect.phone_profile_id = profile.id
        prospect.osint_status = "queued"
        prospect.prospectlab_status = "pending"
        self._db.flush()

        if use_celery:
            return True

        result = asyncio.run(self._osint.enrich_phone_number(phone))
        if not isinstance(result, dict):
            raise RuntimeError("resultat OSINT invalide")
        apply_osint_result_to_profile(self._db, profile, result)
        apply_osint_result_to_prospect(prospect, profile, result)
        self._db.flush()
        return False

    def sync_prospect_from_profile(self, profile_id: int) -> int:
        """
        Met a jour les prospects lies quand un profil OSINT Celery termine.

        @param profile_id ID PhoneNumberProfile.
        @returns Nombre de lignes prospect mises a jour.
        """
        profile = self._db.get(PhoneNumberProfile, profile_id)
        if profile is None:
            return 0
        rows = (
            self._db.query(ProspectPhone)
            .filter(ProspectPhone.phone_profile_id == profile_id)
            .all()
        )
        if not rows:
            digits = "".join(ch for ch in (profile.phone_number or "") if ch.isdigit())
            if digits.startswith("33") and len(digits) == 11:
                digits = "0" + digits[2:]
            rows = (
                self._db.query(ProspectPhone)
                .filter(ProspectPhone.phone_digits == digits)
                .all()
            )
        updated = 0
        for prospect in rows:
            prospect.phone_profile_id = profile.id
            prospect.osint_status = "done"
            prospect.osint_company_name = profile.company_name or profile.name
            prospect.osint_reputation = profile.reputation
            prospect.osint_operator = profile.operator or profile.carrier
            prospect.osint_region = profile.region or profile.city
            if prospect.prospectlab_status == "pending":
                has_pl = any(
                    (s.source_code or "").lower() == "prospectlab"
                    for s in (profile.osint_sources or [])
                )
                prospect.prospectlab_status = "matched" if has_pl else "not_found"
                if has_pl:
                    prospect.prospectlab_name = profile.company_name or profile.name
            prospect.name_match_status = compute_name_match_status(
                prospect.name,
                prospect.prospectlab_name,
                prospect.osint_company_name,
            )
            prospect.enriched_at = datetime.utcnow()
            updated += 1

        batches_touched: Dict[int, ProspectPhoneImportBatch] = {}
        batches_finished: List[int] = []
        if rows:
            batch_ids = {r.import_batch_id for r in rows if r.import_batch_id}
            for bid in batch_ids:
                batch = self._db.get(ProspectPhoneImportBatch, bid)
                if batch and batch.phase == "enrich":
                    batch.enrich_done = min(
                        batch.enrich_total,
                        (batch.enrich_done or 0) + 1,
                    )
                    if batch.enrich_queued > 0:
                        batch.enrich_queued = max(0, batch.enrich_queued - 1)
                    processed = (batch.enrich_done or 0) + (batch.enrich_failed or 0)
                    if processed >= (batch.enrich_total or 0):
                        batch.phase = "done"
                        batches_finished.append(bid)
                    batches_touched[bid] = batch
        self._db.commit()

        for bid in batches_finished:
            batch = batches_touched.get(bid)
            if batch is None:
                continue
            notify_prospect_phone_realtime(
                self._config,
                EventType.PROSPECT_PHONE_ENRICH_COMPLETED.value,
                {
                    "batch_id": bid,
                    "phase": "done",
                    "enrich_total": batch.enrich_total,
                    "enrich_done": batch.enrich_done,
                    "enrich_failed": batch.enrich_failed,
                    "enrich_queued": batch.enrich_queued,
                },
            )

        if updated:
            for prospect in rows:
                batch = batches_touched.get(prospect.import_batch_id or 0)
                payload: Dict[str, Any] = {
                    "batch_id": prospect.import_batch_id,
                    "step": "done",
                    "phase": batch.phase if batch else "enrich",
                    "prospect": prospect_row_event_dict(prospect),
                }
                if batch:
                    payload.update(
                        {
                            "enrich_total": batch.enrich_total,
                            "enrich_done": batch.enrich_done,
                            "enrich_failed": batch.enrich_failed,
                            "enrich_queued": batch.enrich_queued,
                            "current": batch.enrich_done,
                        }
                    )
                notify_prospect_phone_realtime(
                    self._config,
                    EventType.PROSPECT_PHONE_ENRICH_ROW.value,
                    payload,
                )
        return updated
