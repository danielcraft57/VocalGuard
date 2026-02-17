"""
Routes API pour la gestion des clients (mini CRM).
"""

from typing import List

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.orm import Session

from backend.api.models import CustomerCreate, CustomerResponse
from backend.database.database import get_db
from backend.database.models import Customer


router = APIRouter()


@router.get("/customers", response_model=List[CustomerResponse])
async def list_customers(db: Session = Depends(get_db)) -> List[CustomerResponse]:
    """
    Liste les clients connus.
    """
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    return [CustomerResponse.from_orm(c) for c in customers]


@router.post("/customers", response_model=CustomerResponse, status_code=201)
async def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
) -> CustomerResponse:
    """
    Cree un client et le persiste en base.
    """
    customer = Customer(
        phone_number=payload.phone_number,
        email=payload.email,
        name=payload.name,
        company_name=payload.company_name,
        notes=payload.notes,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    
    logger.info(f"Client cree: {customer.id} - {customer.phone_number}")
    return CustomerResponse.from_orm(customer)

