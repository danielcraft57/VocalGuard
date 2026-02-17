"""
Routes API pour la gestion des devis.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from backend.api.models import QuoteCreate, QuoteResponse, QuoteLine
from backend.database.database import get_db
from backend.database.models import Quote


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


@router.get("/quotes", response_model=List[QuoteResponse])
async def list_quotes(db: Session = Depends(get_db)) -> List[QuoteResponse]:
    """
    Liste les devis.
    """
    quotes = db.query(Quote).order_by(Quote.created_at.desc()).all()
    return [QuoteResponse.from_orm(q) for q in quotes]


@router.post("/quotes", response_model=QuoteResponse, status_code=201)
async def create_quote(
    payload: QuoteCreate,
    db: Session = Depends(get_db),
) -> QuoteResponse:
    """
    Cree un devis et le persiste en base.
    """
    total_ht, total_ttc = _compute_totals(payload.lines)
    
    quote = Quote(
        customer_id=payload.customer_id,
        phone_number=payload.phone_number,
        title=payload.title,
        lines=[line.model_dump() for line in payload.lines],
        notes=payload.notes,
        status=payload.status,
        total_ht=total_ht,
        total_ttc=total_ttc,
        created_at=datetime.utcnow(),
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    
    logger.info(f"Devis cree: {quote.id} - {quote.title}")
    return QuoteResponse.from_orm(quote)

