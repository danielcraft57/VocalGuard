"""
Routes API pour la gestion des devis.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.orm import Session, joinedload

from backend.api.models import QuoteCreate, QuoteResponse, QuoteLine
from backend.database.database import get_db
from backend.database.models import Quote, QuoteLine as QuoteLineModel


router = APIRouter()


def _compute_totals(lines: List[QuoteLine]) -> tuple[int, int]:
    """
    Calcule les montants HT et TTC d'un devis.

    Les valeurs sont stockees en centimes pour eviter les problemes
    d'arrondis flottants.
    """
    total_ht_float = sum(line.quantity * line.unit_price for line in lines)
    total_ht_cents = int(round(total_ht_float * 100))
    # Simplification: TTC = HT pour l'instant
    return total_ht_cents, total_ht_cents


def _quote_to_response(quote: Quote) -> QuoteResponse:
    """
    Serialise un devis ORM (lignes en table enfant) vers QuoteResponse.

    @param quote Devis SQLAlchemy avec relation lines chargee.
    @returns Reponse API.
    """
    api_lines = [
        QuoteLine(
            description=line.description,
            quantity=float(line.quantity),
            unit_price=float(line.unit_price),
        )
        for line in (quote.lines or [])
    ]
    return QuoteResponse(
        id=quote.id,
        client_id=quote.client_id,
        phone_number=quote.phone_number,
        title=quote.title,
        lines=api_lines,
        notes=quote.notes,
        status=quote.status or "draft",
        total_ht=float(quote.total_ht or 0),
        total_ttc=float(quote.total_ttc or 0),
        created_at=quote.created_at,
    )


@router.get("/quotes", response_model=List[QuoteResponse])
async def list_quotes(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> List[QuoteResponse]:
    """
    Liste les devis (pagination, lignes en selectinload).
    """
    quotes = (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .order_by(Quote.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_quote_to_response(q) for q in quotes]


@router.post("/quotes", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    db: Session = Depends(get_db),
) -> QuoteResponse:
    """
    Cree un devis et le persiste en base (lignes en quote_lines).
    """
    total_ht, total_ttc = _compute_totals(payload.lines)

    quote = Quote(
        client_id=payload.client_id,
        phone_number=payload.phone_number,
        title=payload.title,
        notes=payload.notes,
        status=payload.status,
        total_ht=total_ht,
        total_ttc=total_ttc,
        created_at=datetime.utcnow(),
    )
    db.add(quote)
    db.flush()
    for idx, line in enumerate(payload.lines):
        db.add(
            QuoteLineModel(
                quote_id=quote.id,
                position=idx,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
            )
        )
    db.commit()
    db.refresh(quote)
    quote = (
        db.query(Quote)
        .options(joinedload(Quote.lines))
        .filter(Quote.id == quote.id)
        .one()
    )

    logger.info(f"Devis cree: {quote.id} - {quote.title}")
    return _quote_to_response(quote)
