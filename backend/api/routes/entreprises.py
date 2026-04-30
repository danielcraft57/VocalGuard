"""
Routes API pour la gestion des entreprises (prospection) et l'import Excel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile, Query, HTTPException
from loguru import logger
import anyio
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy import func
from sqlalchemy import delete as sa_delete

from backend.api.models import (
    EntrepriseCreate,
    EntrepriseUpdate,
    EntrepriseResponse,
    EntrepriseListResponse,
    EntrepriseImportSummary,
    EntrepriseImportRowResponse,
    EntreprisePhoneAnalysisResponse,
)
from backend.database.database import get_db
from backend.database.models import (
    Entreprise,
    EntrepriseEmail,
    EntrepriseImportBatch,
    EntrepriseImportRow,
    EntreprisePhoneAnalysis,
    EntrepriseCategory,
    entreprise_category_links,
)
from backend.services.entreprise_import_service import EntrepriseImportService
from backend.core.events import Event, EventType, event_bus
from backend.database import database as db_module
from backend.database.models import Call


router = APIRouter()


def _digits(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return "".join(ch for ch in s if ch.isdigit()) or None

def _to_entreprise_response(e: Entreprise) -> EntrepriseResponse:
    payload = {
        "id": e.id,
        "name": e.name,
        "website": e.website,
        "phone_number": e.phone_number,
        "phone_digits": e.phone_digits,
        "country": e.country,
        "city": getattr(e, "city", None),
        "address_1": e.address_1,
        "address_2": e.address_2,
        "longitude": e.longitude,
        "latitude": e.latitude,
        "rating": e.rating,
        "reviews_count": e.reviews_count,
        "categories": [c.name for c in (e.categories or [])],
        "emails": sorted([(x.email or "").strip() for x in (e.emails or []) if (x.email or "").strip()]),
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }
    return EntrepriseResponse.model_validate(payload)


def _normalize_emails(values: List[str]) -> List[str]:
    unique = set()
    for item in values:
        raw = (item or "").strip().lower()
        if raw and "@" in raw:
            unique.add(raw)
    return sorted(unique)


def _attach_entreprise_emails(db: Session, entreprise: Entreprise, emails: List[str]) -> None:
    normalized = _normalize_emails(emails)
    if not normalized:
        entreprise.emails = set()
        return
    rows = db.query(EntrepriseEmail).filter(EntrepriseEmail.email.in_(normalized)).all()
    existing_by_email = {row.email: row for row in rows}
    linked = set(rows)
    for email in normalized:
        if email in existing_by_email:
            continue
        created = EntrepriseEmail(email=email)
        db.add(created)
        db.flush()
        linked.add(created)
    entreprise.emails = linked


@router.get("/entreprises", response_model=EntrepriseListResponse)
async def list_entreprises(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="Recherche texte (nom, tel, pays, adresse, categorie)"),
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="Filtre categorie (nom)"),
    has_phone: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
) -> EntrepriseListResponse:
    base = db.query(Entreprise)

    if country:
        base = base.filter(Entreprise.country.ilike(country.strip()))  # type: ignore[attr-defined]

    if city:
        base = base.filter(Entreprise.city.ilike(city.strip()))  # type: ignore[attr-defined]

    if category and category.strip():
        needle_cat = f"%{category.strip()}%"
        base = base.filter(
            Entreprise.categories.any(EntrepriseCategory.name.ilike(needle_cat))  # type: ignore[attr-defined]
        )

    if has_phone is True:
        base = base.filter(Entreprise.phone_digits.isnot(None))
    elif has_phone is False:
        base = base.filter(Entreprise.phone_digits.is_(None))

    if q and q.strip():
        needle = f"%{q.strip()}%"
        base = base.filter(
            or_(
                Entreprise.name.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.phone_number.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.country.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.city.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.address_1.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.address_2.ilike(needle),  # type: ignore[attr-defined]
                Entreprise.categories.any(EntrepriseCategory.name.ilike(needle)),  # type: ignore[attr-defined]
            )
        )

    total = base.count()
    entreprises = (
        base.order_by(Entreprise.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return EntrepriseListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[_to_entreprise_response(e) for e in entreprises],
    )


@router.delete("/entreprises/{entreprise_id}", status_code=204)
async def delete_entreprise(
    entreprise_id: int,
    db: Session = Depends(get_db),
) -> None:
    e = db.get(Entreprise, entreprise_id)  # type: ignore[arg-type]
    if not e:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    db.query(EntreprisePhoneAnalysis).filter(EntreprisePhoneAnalysis.entreprise_id == entreprise_id).delete(synchronize_session=False)
    db.query(EntrepriseImportRow).filter(EntrepriseImportRow.entreprise_id == entreprise_id).update(
        {"entreprise_id": None},
        synchronize_session=False,
    )
    db.execute(sa_delete(entreprise_category_links).where(entreprise_category_links.c.entreprise_id == entreprise_id))
    db.delete(e)
    db.commit()
    return None


@router.delete("/entreprises", status_code=200)
async def delete_entreprises_bulk(
    ids: List[int] = Query(..., description="IDs à supprimer, ex: ?ids=1&ids=2"),
    db: Session = Depends(get_db),
) -> dict:
    if not ids:
        raise HTTPException(status_code=400, detail="Liste d'ids vide")
    db.query(EntreprisePhoneAnalysis).filter(EntreprisePhoneAnalysis.entreprise_id.in_(ids)).delete(synchronize_session=False)
    db.query(EntrepriseImportRow).filter(EntrepriseImportRow.entreprise_id.in_(ids)).update(
        {"entreprise_id": None},
        synchronize_session=False,
    )
    db.execute(sa_delete(entreprise_category_links).where(entreprise_category_links.c.entreprise_id.in_(ids)))
    q = db.query(Entreprise).filter(Entreprise.id.in_(ids))
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return {"deleted": int(deleted)}


@router.get("/entreprises/{entreprise_id}", response_model=EntrepriseResponse)
async def get_entreprise(
    entreprise_id: int,
    db: Session = Depends(get_db),
) -> EntrepriseResponse:
    e = db.get(Entreprise, entreprise_id)  # type: ignore[arg-type]
    if not e:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    return _to_entreprise_response(e)


@router.get("/entreprises/{entreprise_id}/call-stats")
async def get_entreprise_call_stats(
    entreprise_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """
    Stats simples d'appels liés à l'entreprise (par match tolerant sur téléphone).
    Objectif: pilotage prospection (passés / répondus / raccrochés / non répondus).
    """
    e = db.get(Entreprise, entreprise_id)  # type: ignore[arg-type]
    if not e:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")

    digits = e.phone_digits or _digits(e.phone_number)
    if not digits:
        return {"total": 0, "by_status": {}, "note": "Entreprise sans téléphone"}

    like = f"%{digits}%"
    rows = (
        db.query(Call.status, func.count(Call.id))
        .filter(Call.phone_number.isnot(None))
        .filter(Call.phone_number.ilike(like))  # type: ignore[attr-defined]
        .group_by(Call.status)
        .all()
    )
    by_status = {status: int(cnt) for (status, cnt) in rows if status}
    total = sum(by_status.values())
    return {"total": total, "by_status": by_status}


@router.post("/entreprises", response_model=EntrepriseResponse, status_code=201)
async def create_entreprise(
    payload: EntrepriseCreate,
    db: Session = Depends(get_db),
) -> EntrepriseResponse:
    data = payload.model_dump()
    emails = data.pop("emails", [])
    e = Entreprise(**data)
    db.add(e)
    _attach_entreprise_emails(db, e, emails)
    db.commit()
    db.refresh(e)
    return _to_entreprise_response(e)


@router.patch("/entreprises/{entreprise_id}", response_model=EntrepriseResponse)
async def update_entreprise(
    entreprise_id: int,
    payload: EntrepriseUpdate,
    db: Session = Depends(get_db),
) -> EntrepriseResponse:
    e = db.get(Entreprise, entreprise_id)  # type: ignore[arg-type]
    if not e:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    updates = payload.model_dump(exclude_unset=True)
    emails = updates.pop("emails", None)
    for key, value in updates.items():
        setattr(e, key, value)
    if emails is not None:
        _attach_entreprise_emails(db, e, emails)
    db.commit()
    db.refresh(e)
    return _to_entreprise_response(e)


@router.post("/entreprises/import", response_model=EntrepriseImportSummary, status_code=201)
async def import_entreprises_xlsx(
    file: UploadFile = File(...),
    analyze_phone: bool = True,
    db: Session = Depends(get_db),
) -> EntrepriseImportSummary:
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .xlsx sont supportes pour l'instant")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")

    # Créer un batch immédiatement et retourner tout de suite (le traitement part en arrière-plan).
    batch = EntrepriseImportBatch(
        original_filename=file.filename,
        source="excel",
        total_rows=0,
        imported_rows=0,
        skipped_with_website=0,
        skipped_invalid=0,
        skipped_duplicates=0,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    await event_bus.publish(
        Event(
            event_type=EventType.ENTREPRISE_IMPORT_STARTED,
            timestamp=datetime.utcnow(),
            data={"batch_id": batch.id, "filename": file.filename, "analyze_phone": analyze_phone},
            source="EntrepriseImport",
        )
    )

    async def _publish_progress(payload: dict) -> None:
        # Inclure aussi total_rows quand il est connu
        try:
            b = None
            if db_module.SessionLocal is not None:
                tmp = db_module.SessionLocal()
                try:
                    b = tmp.get(EntrepriseImportBatch, payload.get("batch_id"))  # type: ignore[arg-type]
                finally:
                    tmp.close()
            if b and b.total_rows:
                payload = {**payload, "total_rows": b.total_rows}
        except Exception:
            pass
        await event_bus.publish(
            Event(
                event_type=EventType.ENTREPRISE_IMPORT_PROGRESS,
                timestamp=datetime.utcnow(),
                data=payload,
                source="EntrepriseImport",
            )
        )

    async def _run_background_import() -> None:
        # Nouveau scope DB dans la tâche de fond (la session FastAPI du handler va se fermer).
        if db_module.SessionLocal is None:
            # Sécurité: si l'app n'a pas initialisé la DB, on ne peut pas traiter.
            return
        bg_db = db_module.SessionLocal()
        try:
            service = EntrepriseImportService(bg_db)

            def progress_cb(p: dict) -> None:
                anyio.from_thread.run(_publish_progress, p)

            def run_sync() -> None:
                service.import_xlsx(
                    xlsx_bytes=content,
                    original_filename=file.filename,
                    source="excel",
                    analyze_phone=analyze_phone,
                    batch_id=batch.id,
                    progress_callback=progress_cb,
                )

            await anyio.to_thread.run_sync(run_sync)

            b2 = bg_db.get(EntrepriseImportBatch, batch.id)  # type: ignore[arg-type]
            await event_bus.publish(
                Event(
                    event_type=EventType.ENTREPRISE_IMPORT_COMPLETED,
                    timestamp=datetime.utcnow(),
                    data={
                        "batch_id": batch.id,
                        "total_rows": b2.total_rows if b2 else None,
                        "imported_rows": b2.imported_rows if b2 else None,
                        "skipped_with_website": b2.skipped_with_website if b2 else None,
                        "skipped_invalid": b2.skipped_invalid if b2 else None,
                        "skipped_duplicates": b2.skipped_duplicates if b2 else None,
                    },
                    source="EntrepriseImport",
                )
            )
        except Exception as exc:
            logger.exception("Import entreprises (background) échoué: {}", exc)
            await event_bus.publish(
                Event(
                    event_type=EventType.ENTREPRISE_IMPORT_FAILED,
                    timestamp=datetime.utcnow(),
                    data={"batch_id": batch.id, "error": str(exc)},
                    source="EntrepriseImport",
                )
            )
        finally:
            try:
                bg_db.close()
            except Exception:
                pass

    asyncio.create_task(_run_background_import())

    return EntrepriseImportSummary(
        batch_id=batch.id,
        original_filename=batch.original_filename,
        total_rows=batch.total_rows,
        imported_rows=batch.imported_rows,
        skipped_with_website=batch.skipped_with_website,
        skipped_invalid=batch.skipped_invalid,
        skipped_duplicates=batch.skipped_duplicates,
    )


@router.get("/entreprises/import-batches/{batch_id}", response_model=EntrepriseImportSummary)
async def get_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
) -> EntrepriseImportSummary:
    b = db.get(EntrepriseImportBatch, batch_id)  # type: ignore[arg-type]
    if not b:
        raise HTTPException(status_code=404, detail="Batch introuvable")
    return EntrepriseImportSummary(
        batch_id=b.id,
        original_filename=b.original_filename,
        total_rows=b.total_rows,
        imported_rows=b.imported_rows,
        skipped_with_website=b.skipped_with_website,
        skipped_invalid=b.skipped_invalid,
        skipped_duplicates=b.skipped_duplicates,
    )


@router.get("/entreprises/import-batches/{batch_id}/rows", response_model=List[EntrepriseImportRowResponse])
async def list_import_rows(
    batch_id: int,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[EntrepriseImportRowResponse]:
    q = db.query(EntrepriseImportRow).filter(EntrepriseImportRow.batch_id == batch_id)
    if status:
        q = q.filter(EntrepriseImportRow.status == status)
    rows = (
        q.order_by(EntrepriseImportRow.row_number.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [EntrepriseImportRowResponse.model_validate(r) for r in rows]


@router.get("/entreprises/{entreprise_id}/phone-analyses", response_model=List[EntreprisePhoneAnalysisResponse])
async def list_phone_analyses(
    entreprise_id: int,
    db: Session = Depends(get_db),
) -> List[EntreprisePhoneAnalysisResponse]:
    items = (
        db.query(EntreprisePhoneAnalysis)
        .filter(EntreprisePhoneAnalysis.entreprise_id == entreprise_id)
        .order_by(EntreprisePhoneAnalysis.created_at.desc())
        .all()
    )
    return [EntreprisePhoneAnalysisResponse.model_validate(x) for x in items]

