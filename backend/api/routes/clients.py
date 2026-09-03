"""
Routes API pour la gestion des clients (contacts / personnes).
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.orm import Session

from backend.api.models import ClientCreate, ClientResponse
from backend.database.database import get_db
from backend.database.models import Client

router = APIRouter()


@router.get("/clients", response_model=List[ClientResponse])
async def list_clients(
    db: Session = Depends(get_db),
    entreprise_id: Optional[int] = Query(None, description="Filtrer par entreprise"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
) -> List[ClientResponse]:
    q = db.query(Client).order_by(Client.created_at.desc())
    if entreprise_id is not None:
        q = q.filter(Client.entreprise_id == entreprise_id)
    rows = q.offset(skip).limit(limit).all()
    return [ClientResponse.from_orm(c) for c in rows]


@router.post("/clients", response_model=ClientResponse, status_code=201)
async def create_client(payload: ClientCreate, db: Session = Depends(get_db)) -> ClientResponse:
    client = Client(
        entreprise_id=payload.entreprise_id,
        phone_number=payload.phone_number,
        email=payload.email,
        name=payload.name,
        notes=payload.notes,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    logger.info(f"Client cree: {client.id} - {client.phone_number}")
    return ClientResponse.from_orm(client)

