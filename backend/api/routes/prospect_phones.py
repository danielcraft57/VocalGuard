"""
Routes API : prospects telephoniques (import ProspectLab + verification).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.api.models import (
    PhoneNumberProfileResponse,
    ProspectPhoneCreate,
    ProspectPhoneDetailResponse,
    ProspectPhoneImportSummary,
    ProspectPhoneListResponse,
    ProspectPhoneResponse,
    ProspectPhoneUpdate,
)
from backend.core.config import Config
from backend.core.events import Event, EventType, event_bus
from backend.core.recent_logs import push_recent_log, recent_logs
from backend.database import database as db_module
from backend.database.database import get_db
from backend.database.models import (
    PhoneNumberProfile,
    ProspectPhone,
    ProspectPhoneCategory,
    ProspectPhoneGoogleType,
    ProspectPhoneImportBatch,
    prospect_phone_category_links,
    prospect_phone_google_type_links,
)
from backend.services.entreprise_import_service import _phone_digits
from backend.services.prospect_phone_enrichment_service import (
    ProspectPhoneEnrichmentService,
    _thread_enrich_one,
    default_enrich_parallel,
    enrich_engine_label,
)
from backend.services.prospect_phone_import_service import ProspectPhoneImportService

router = APIRouter()

_VERIFICATION_STATUSES = frozenset(
    {
        "pending",
        "line_ok",
        "line_fail",
        "voicemail",
        "company_ok",
        "company_mismatch",
        "skipped",
    }
)


def _batch_summary(b: ProspectPhoneImportBatch) -> ProspectPhoneImportSummary:
    return ProspectPhoneImportSummary(
        batch_id=b.id,
        original_filename=b.original_filename,
        source_city=b.source_city,
        total_rows=b.total_rows,
        imported_rows=b.imported_rows,
        skipped_with_website=b.skipped_with_website,
        skipped_invalid=b.skipped_invalid,
        skipped_duplicates=b.skipped_duplicates,
        phase=b.phase or "pending",
        enrich_total=b.enrich_total or 0,
        enrich_done=b.enrich_done or 0,
        enrich_failed=b.enrich_failed or 0,
        enrich_queued=b.enrich_queued or 0,
        last_error=b.last_error,
    )


def _to_response(p: ProspectPhone) -> ProspectPhoneResponse:
    return ProspectPhoneResponse(
        id=p.id,
        name=p.name,
        phone_number=p.phone_number,
        phone_digits=p.phone_digits,
        source_city=p.source_city,
        country=p.country,
        city=p.city,
        postal_code=p.postal_code,
        address_1=p.address_1,
        address_2=p.address_2,
        longitude=p.longitude,
        latitude=p.latitude,
        rating=p.rating,
        reviews_count=p.reviews_count,
        google_categories_raw=p.google_categories_raw,
        category_translate_raw=getattr(p, "category_translate_raw", None),
        categories=sorted([c.name for c in (p.categories or [])]),
        google_types=sorted([g.label for g in (getattr(p, "google_types", None) or [])]),
        website=getattr(p, "website", None),
        phone_profile_id=getattr(p, "phone_profile_id", None),
        osint_status=getattr(p, "osint_status", None) or "pending",
        prospectlab_status=getattr(p, "prospectlab_status", None) or "pending",
        prospectlab_entreprise_id=getattr(p, "prospectlab_entreprise_id", None),
        prospectlab_name=getattr(p, "prospectlab_name", None),
        osint_company_name=getattr(p, "osint_company_name", None),
        osint_reputation=getattr(p, "osint_reputation", None),
        osint_operator=getattr(p, "osint_operator", None),
        osint_region=getattr(p, "osint_region", None),
        name_match_status=getattr(p, "name_match_status", None),
        enriched_at=getattr(p, "enriched_at", None),
        verification_status=p.verification_status,
        verification_notes=p.verification_notes,
        verified_at=p.verified_at,
        last_call_id=p.last_call_id,
        import_batch_id=p.import_batch_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/prospect-phones/enrich-capabilities")
async def prospect_enrich_capabilities() -> dict:
    """Indique si l'OSINT distant (ex. node15) et le parallelisme sont actifs."""
    from urllib.parse import urlparse

    app_config = Config()
    url = (getattr(app_config, "osint_service_url", None) or "").strip().rstrip("/")
    host = urlparse(url).hostname if url else None
    return {
        "osint_remote": bool(url),
        "osint_host": host,
        "enrich_engine": enrich_engine_label(app_config),
        "default_parallel": default_enrich_parallel(app_config),
        "celery_available": ProspectPhoneEnrichmentService.celery_available(),
    }


@router.get("/prospect-phones/server-logs")
async def prospect_server_logs(limit: int = Query(40, ge=1, le=80)) -> dict:
    """Derniers messages backend (erreurs SQL, import) pour l'UI."""
    return {"lines": recent_logs(limit)}


@router.get("/prospect-phones", response_model=ProspectPhoneListResponse)
async def list_prospect_phones(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None),
    source_city: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    verification_status: Optional[str] = Query(None),
    osint_status: Optional[str] = Query(None),
    prospectlab_status: Optional[str] = Query(None),
    name_match_status: Optional[str] = Query(None),
    import_batch_id: Optional[int] = Query(None),
    has_phone: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
) -> ProspectPhoneListResponse:
    """Liste paginee des prospects normalises."""
    base = db.query(ProspectPhone).options(
        selectinload(ProspectPhone.categories),
        selectinload(ProspectPhone.google_types),
    )

    if source_city:
        base = base.filter(ProspectPhone.source_city.ilike(source_city.strip()))  # type: ignore[attr-defined]
    if city:
        base = base.filter(ProspectPhone.city.ilike(city.strip()))  # type: ignore[attr-defined]
    if verification_status:
        st = verification_status.strip().lower()
        if st not in _VERIFICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Statut de verification inconnu")
        base = base.filter(ProspectPhone.verification_status == st)
    if osint_status:
        base = base.filter(ProspectPhone.osint_status == osint_status.strip().lower())
    if prospectlab_status:
        base = base.filter(ProspectPhone.prospectlab_status == prospectlab_status.strip().lower())
    if name_match_status:
        base = base.filter(ProspectPhone.name_match_status == name_match_status.strip().lower())
    if import_batch_id is not None:
        base = base.filter(ProspectPhone.import_batch_id == import_batch_id)
    if has_phone is True:
        base = base.filter(ProspectPhone.phone_digits.isnot(None))
    elif has_phone is False:
        base = base.filter(ProspectPhone.phone_digits.is_(None))

    if q:
        needle = f"%{q.strip()}%"
        base = base.filter(
            or_(
                ProspectPhone.name.ilike(needle),  # type: ignore[attr-defined]
                ProspectPhone.phone_number.ilike(needle),  # type: ignore[attr-defined]
                ProspectPhone.address_1.ilike(needle),  # type: ignore[attr-defined]
                ProspectPhone.address_2.ilike(needle),  # type: ignore[attr-defined]
            )
        )

    total = base.count()
    rows = (
        base.order_by(ProspectPhone.source_city.asc(), ProspectPhone.name.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return ProspectPhoneListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_to_response(r) for r in rows],
    )


@router.get("/prospect-phones/source-cities", response_model=List[str])
async def list_source_cities(db: Session = Depends(get_db)) -> List[str]:
    """Villes deduites des noms de fichiers importes (filtre UI)."""
    rows = (
        db.query(ProspectPhone.source_city)
        .filter(ProspectPhone.source_city.isnot(None))
        .distinct()
        .order_by(ProspectPhone.source_city.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.get("/prospect-phones/stats/summary")
async def prospect_phones_summary(db: Session = Depends(get_db)) -> dict:
    """Compteurs par statut de verification."""
    rows = (
        db.query(ProspectPhone.verification_status, func.count(ProspectPhone.id))
        .group_by(ProspectPhone.verification_status)
        .all()
    )
    by_status = {str(status): int(count) for status, count in rows}
    total = sum(by_status.values())
    return {"total": total, "by_status": by_status}


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    """Chaine vide devient None."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _assign_phone(db: Session, row: ProspectPhone, phone: Optional[str]) -> None:
    """
    Enregistre le numero affiche et sa forme normalisee.

    @param db Session SQLAlchemy.
    @param row Prospect a mettre a jour.
    @param phone Numero saisi, ou vide pour l'effacer.
    @throws HTTPException 409 si un autre prospect a deja ce numero.
    """
    raw = _blank_to_none(phone)
    digits = _phone_digits(raw) if raw else None
    if digits:
        taken = (
            db.query(ProspectPhone.id)
            .filter(ProspectPhone.phone_digits == digits, ProspectPhone.id != row.id)
            .first()
        )
        if taken:
            raise HTTPException(status_code=409, detail="Ce numero est deja dans la liste")
    row.phone_number = raw
    row.phone_digits = digits or None


_TEXT_FIELDS = (
    "source_city",
    "city",
    "postal_code",
    "address_1",
    "address_2",
    "website",
    "country",
    "verification_notes",
)


def _load_prospect_row(db: Session, prospect_id: int) -> ProspectPhone:
    """Charge un prospect avec categories et types Google."""
    row = (
        db.query(ProspectPhone)
        .options(
            selectinload(ProspectPhone.categories),
            selectinload(ProspectPhone.google_types),
        )
        .filter(ProspectPhone.id == prospect_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    return row


def _load_osint_profile_for_prospect(db: Session, prospect: ProspectPhone) -> Optional[PhoneNumberProfile]:
    """Retourne le profil OSINT lie au prospect, si present."""
    profile: Optional[PhoneNumberProfile] = None
    if prospect.phone_profile_id:
        profile = (
            db.query(PhoneNumberProfile)
            .options(joinedload(PhoneNumberProfile.osint_sources))
            .filter(PhoneNumberProfile.id == prospect.phone_profile_id)
            .one_or_none()
        )
    phone = (prospect.phone_number or "").strip()
    if profile is None and phone:
        profile = (
            db.query(PhoneNumberProfile)
            .options(joinedload(PhoneNumberProfile.osint_sources))
            .filter(PhoneNumberProfile.phone_number == phone)
            .order_by(PhoneNumberProfile.last_checked_at.desc().nullslast())
            .first()
        )
    return profile


def _to_detail(db: Session, prospect: ProspectPhone) -> ProspectPhoneDetailResponse:
    """Assemble prospect + profil OSINT pour l'UI detail."""
    profile = _load_osint_profile_for_prospect(db, prospect)
    osint_resp = PhoneNumberProfileResponse.from_orm(profile) if profile else None
    return ProspectPhoneDetailResponse(prospect=_to_response(prospect), osint_profile=osint_resp)


@router.get("/prospect-phones/{prospect_id}", response_model=ProspectPhoneResponse)
async def get_prospect_phone(prospect_id: int, db: Session = Depends(get_db)) -> ProspectPhoneResponse:
    """Lit un prospect."""
    return _to_response(_load_prospect_row(db, prospect_id))


@router.get("/prospect-phones/{prospect_id}/detail", response_model=ProspectPhoneDetailResponse)
async def get_prospect_phone_detail(
    prospect_id: int,
    db: Session = Depends(get_db),
) -> ProspectPhoneDetailResponse:
    """Lit un prospect et le profil OSINT associe."""
    return _to_detail(db, _load_prospect_row(db, prospect_id))


@router.post("/prospect-phones/{prospect_id}/enrich", response_model=ProspectPhoneDetailResponse)
async def enrich_prospect_phone_again(
    prospect_id: int,
    db: Session = Depends(get_db),
) -> ProspectPhoneDetailResponse:
    """
    Relance OSINT + ProspectLab pour une ligne (synchrone, sans Celery).

    Utile quand l'import initial a echoue ou que les sources ont ete mises a jour.
    """
    row = _load_prospect_row(db, prospect_id)
    if not (row.phone_number or "").strip():
        raise HTTPException(status_code=400, detail="Aucun numero a enrichir")

    app_config = Config()

    def _run() -> tuple:
        return _thread_enrich_one(prospect_id, app_config)

    _pid, status, _payload, err = await anyio.to_thread.run_sync(_run)
    if status == "failed":
        raise HTTPException(status_code=502, detail=err or "Enrichissement echoue")

    db.expire_all()
    return _to_detail(db, _load_prospect_row(db, prospect_id))


@router.post("/prospect-phones", response_model=ProspectPhoneResponse, status_code=201)
async def create_prospect_phone(
    payload: ProspectPhoneCreate,
    db: Session = Depends(get_db),
) -> ProspectPhoneResponse:
    """Cree un prospect a la main."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom est obligatoire")
    row = ProspectPhone(name=name, verification_status=payload.verification_status or "pending")
    db.add(row)
    db.flush()
    _assign_phone(db, row, payload.phone_number)
    for key in _TEXT_FIELDS:
        setattr(row, key, _blank_to_none(getattr(payload, key)))
    if row.verification_status != "pending":
        row.verified_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.delete("/prospect-phones")
async def delete_all_prospect_phones(db: Session = Depends(get_db)) -> dict:
    """Supprime tous les prospects, leurs liens et les lots d'import."""
    deleted = db.query(ProspectPhone).count()
    db.execute(sa_delete(prospect_phone_category_links))
    db.execute(sa_delete(prospect_phone_google_type_links))
    db.query(ProspectPhone).delete(synchronize_session=False)
    db.query(ProspectPhoneCategory).delete(synchronize_session=False)
    db.query(ProspectPhoneGoogleType).delete(synchronize_session=False)
    db.query(ProspectPhoneImportBatch).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.delete("/prospect-phones/{prospect_id}")
async def delete_prospect_phone(prospect_id: int, db: Session = Depends(get_db)) -> dict:
    """Supprime un prospect."""
    row = db.query(ProspectPhone).filter(ProspectPhone.id == prospect_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    row.categories.clear()
    row.google_types.clear()
    db.delete(row)
    db.commit()
    return {"deleted": 1, "id": prospect_id}


@router.patch("/prospect-phones/{prospect_id}", response_model=ProspectPhoneResponse)
async def update_prospect_phone(
    prospect_id: int,
    payload: ProspectPhoneUpdate,
    db: Session = Depends(get_db),
) -> ProspectPhoneResponse:
    """Met a jour les champs envoyes (nom, numero, adresse, statut, notes)."""
    row = (
        db.query(ProspectPhone)
        .options(
            selectinload(ProspectPhone.categories),
            selectinload(ProspectPhone.google_types),
        )
        .filter(ProspectPhone.id == prospect_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = (data.pop("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Le nom est obligatoire")
        row.name = name
    if "phone_number" in data:
        _assign_phone(db, row, data.pop("phone_number"))
    if "verification_status" in data:
        st = (data.pop("verification_status") or "").strip().lower()
        if st not in _VERIFICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Statut de verification inconnu")
        row.verification_status = st
        if st != "pending" and data.get("verified_at") is None and row.verified_at is None:
            row.verified_at = datetime.utcnow()
    for key, value in data.items():
        if key in _TEXT_FIELDS:
            setattr(row, key, _blank_to_none(value))
        else:
            setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return _to_response(row)


class ProspectPhoneImportDirectoryBody(BaseModel):
    """Import de tous les xlsx d'un dossier local (machine serveur)."""

    directory_path: Optional[str] = Field(
        default=None,
        description="Chemin absolu ; defaut: variable PROSPECT_LAB_DATA_DIR",
    )


@router.post("/prospect-phones/import", response_model=ProspectPhoneImportSummary, status_code=201)
async def import_prospect_phones_xlsx(
    file: UploadFile = File(...),
    run_osint: bool = Query(True, description="Enrichir OSINT + ProspectLab apres import"),
    db: Session = Depends(get_db),
) -> ProspectPhoneImportSummary:
    """Importe un fichier Excel vers prospect_phones (traitement async)."""
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .xlsx sont supportes")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")

    batch = ProspectPhoneImportBatch(
        original_filename=file.filename,
        source="excel",
        phase="pending",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    await event_bus.publish(
        Event(
            event_type=EventType.PROSPECT_PHONE_IMPORT_STARTED,
            timestamp=datetime.utcnow(),
            data={"batch_id": batch.id, "filename": file.filename},
            source="ProspectPhoneImport",
        )
    )

    async def _publish_progress(payload: dict) -> None:
        await event_bus.publish(
            Event(
                event_type=EventType.PROSPECT_PHONE_IMPORT_PROGRESS,
                timestamp=datetime.utcnow(),
                data=payload,
                source="ProspectPhoneImport",
            )
        )

    async def _run_background_import() -> None:
        if db_module.SessionLocal is None:
            return
        bg_db = db_module.SessionLocal()
        try:
            service = ProspectPhoneImportService(bg_db)

            def progress_cb(p: dict) -> None:
                anyio.from_thread.run(_publish_progress, p)

            def run_sync() -> None:
                service.import_xlsx(
                    xlsx_bytes=content,
                    original_filename=file.filename,
                    source="excel",
                    batch_id=batch.id,
                    progress_callback=progress_cb,
                )

            await anyio.to_thread.run_sync(run_sync)

            b2 = bg_db.get(ProspectPhoneImportBatch, batch.id)
            await event_bus.publish(
                Event(
                    event_type=EventType.PROSPECT_PHONE_IMPORT_COMPLETED,
                    timestamp=datetime.utcnow(),
                    data={
                        "batch_id": batch.id,
                        "total_rows": b2.total_rows if b2 else None,
                        "imported_rows": b2.imported_rows if b2 else None,
                        "skipped_with_website": b2.skipped_with_website if b2 else None,
                        "skipped_invalid": b2.skipped_invalid if b2 else None,
                        "skipped_duplicates": b2.skipped_duplicates if b2 else None,
                        "phase": b2.phase if b2 else None,
                    },
                    source="ProspectPhoneImport",
                )
            )

            if run_osint and b2 and (b2.imported_rows or 0) > 0:
                enrich = ProspectPhoneEnrichmentService(bg_db)

                async def _publish_enrich(payload: dict) -> None:
                    event_type = (
                        EventType.PROSPECT_PHONE_ENRICH_ROW
                        if payload.get("prospect")
                        else EventType.PROSPECT_PHONE_ENRICH_PROGRESS
                    )
                    await event_bus.publish(
                        Event(
                            event_type=event_type,
                            timestamp=datetime.utcnow(),
                            data=payload,
                            source="ProspectPhoneEnrich",
                        )
                    )

                def enrich_cb(p: dict) -> None:
                    anyio.from_thread.run(_publish_enrich, p)

                def run_enrich() -> None:
                    enrich.enrich_batch(batch.id, progress_callback=enrich_cb)

                await anyio.to_thread.run_sync(run_enrich)
                b3 = bg_db.get(ProspectPhoneImportBatch, batch.id)
                await event_bus.publish(
                    Event(
                        event_type=EventType.PROSPECT_PHONE_ENRICH_COMPLETED,
                        timestamp=datetime.utcnow(),
                        data={
                            "batch_id": batch.id,
                            "phase": b3.phase if b3 else None,
                            "enrich_total": b3.enrich_total if b3 else None,
                            "enrich_done": b3.enrich_done if b3 else None,
                            "enrich_failed": b3.enrich_failed if b3 else None,
                        },
                        source="ProspectPhoneEnrich",
                    )
                )
        except Exception as exc:
            logger.exception("Import prospect_phones (background) echoue: {}", exc)
            push_recent_log("ERROR", f"Import batch {batch.id}: {exc}")
            try:
                failed = bg_db.get(ProspectPhoneImportBatch, batch.id)
                if failed is not None:
                    failed.phase = "failed"
                    failed.last_error = str(exc)[:500]
                    bg_db.commit()
            except Exception:
                bg_db.rollback()
            await event_bus.publish(
                Event(
                    event_type=EventType.PROSPECT_PHONE_IMPORT_FAILED,
                    timestamp=datetime.utcnow(),
                    data={"batch_id": batch.id, "error": str(exc)},
                    source="ProspectPhoneImport",
                )
            )
        finally:
            try:
                bg_db.close()
            except Exception:
                pass

    asyncio.create_task(_run_background_import())

    return _batch_summary(batch)


@router.get("/prospect-phones/import-batches/{batch_id}", response_model=ProspectPhoneImportSummary)
async def get_prospect_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
) -> ProspectPhoneImportSummary:
    """Etat d'un lot d'import (polling UI)."""
    b = db.get(ProspectPhoneImportBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Batch introuvable")
    return _batch_summary(b)


@router.post("/prospect-phones/import-directory")
async def import_prospect_phones_directory(
    body: ProspectPhoneImportDirectoryBody,
    db: Session = Depends(get_db),
) -> dict:
    """
    Importe tous les .xlsx d'un dossier (chemin sur le serveur API).

    Utile en dev avec PROSPECT_LAB_DATA_DIR pointant vers ProspectLab/Data/...
    """
    raw = (body.directory_path or os.environ.get("PROSPECT_LAB_DATA_DIR") or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="directory_path requis ou PROSPECT_LAB_DATA_DIR non configure",
        )
    directory = Path(raw).resolve()
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Dossier introuvable: {directory}")

    service = ProspectPhoneImportService(db)

    def run_sync():
        return service.import_directory(directory)

    results = await anyio.to_thread.run_sync(run_sync)
    return {
        "directory": str(directory),
        "files": len(results),
        "imported_total": sum(r.imported_rows for r in results),
        "batches": [
            {
                "batch_id": r.batch_id,
                "filename": r.original_filename,
                "source_city": r.source_city,
                "imported_rows": r.imported_rows,
                "skipped_duplicates": r.skipped_duplicates,
            }
            for r in results
        ],
    }
