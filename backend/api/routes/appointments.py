"""
Routes API pour la gestion des rendez-vous.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from backend.api.models import AppointmentCreate, AppointmentResponse
from backend.database.database import get_db
from backend.database.models import Appointment


router = APIRouter()


@router.get("/appointments", response_model=List[AppointmentResponse])
async def list_appointments(db: Session = Depends(get_db)) -> List[AppointmentResponse]:
    """
    Liste les rendez-vous connus.
    """
    appointments = db.query(Appointment).order_by(Appointment.start_time.desc()).all()
    return [AppointmentResponse.from_orm(a) for a in appointments]


@router.post("/appointments", response_model=AppointmentResponse, status_code=201)
async def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
) -> AppointmentResponse:
    """
    Cree un rendez-vous et le persiste en base.
    """
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="L'heure de fin doit etre apres l'heure de debut.")
    
    appointment = Appointment(
        customer_id=payload.customer_id,
        phone_number=payload.phone_number,
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        status=payload.status,
        service_type=payload.service_type,
        notes=payload.notes,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    logger.info(f"RDV cree: {appointment.id} - {appointment.title}")
    return AppointmentResponse.from_orm(appointment)

