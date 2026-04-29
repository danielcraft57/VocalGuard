"""Routes API pour la gestion des rendez-vous et des disponibilites agenda."""

from datetime import datetime, time
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from backend.api.models import (
    AppointmentCreate,
    AppointmentNonWorkingDayCreate,
    AppointmentNonWorkingDayResponse,
    AppointmentResponse,
    AppointmentSettingsBase,
    AppointmentSettingsResponse,
    AppointmentUpdate,
)
from backend.database.database import get_db
from backend.database.models import Appointment, AppointmentNonWorkingDay, AppointmentSettings, Call

router = APIRouter()
_ml_brain = None


def _get_ml_brain():
    """Instancie (une fois) le cerveau ML intents pour enrichir le contexte agenda."""
    global _ml_brain
    if _ml_brain is not None:
        return _ml_brain
    try:
        from backend.ml.ml_intents import CommercialMlConversationBrain

        project_root = Path(__file__).resolve().parents[3]
        _ml_brain = CommercialMlConversationBrain(project_root)
    except Exception:
        _ml_brain = None
    return _ml_brain


def _get_or_create_settings(db: Session) -> AppointmentSettings:
    settings = db.query(AppointmentSettings).order_by(AppointmentSettings.id.asc()).first()
    if settings:
        return settings
    settings = AppointmentSettings(
        timezone="Europe/Paris",
        work_day_start=time(hour=8, minute=30),
        work_day_end=time(hour=18, minute=0),
        slot_minutes=60,
        monday_enabled=True,
        tuesday_enabled=True,
        wednesday_enabled=True,
        thursday_enabled=True,
        friday_enabled=True,
        saturday_enabled=False,
        sunday_enabled=False,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _is_enabled_weekday(settings: AppointmentSettings, weekday: int) -> bool:
    mapping = {
        0: settings.monday_enabled,
        1: settings.tuesday_enabled,
        2: settings.wednesday_enabled,
        3: settings.thursday_enabled,
        4: settings.friday_enabled,
        5: settings.saturday_enabled,
        6: settings.sunday_enabled,
    }
    return bool(mapping.get(weekday, False))


def _assert_appointment_allowed(
    db: Session,
    settings: AppointmentSettings,
    start_time: datetime,
    end_time: datetime,
    appointment_id_to_ignore: Optional[int] = None,
) -> None:
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="L'heure de fin doit etre apres l'heure de debut.")
    if not _is_enabled_weekday(settings, start_time.weekday()):
        raise HTTPException(status_code=400, detail="Ce jour est desactive dans les jours de travail.")
    if start_time.time() < settings.work_day_start or end_time.time() > settings.work_day_end:
        raise HTTPException(status_code=400, detail="Le rendez-vous est hors plage horaire de travail.")

    blocked_day = (
        db.query(AppointmentNonWorkingDay)
        .filter(AppointmentNonWorkingDay.date == start_time.date())
        .first()
    )
    if blocked_day:
        raise HTTPException(status_code=400, detail=f"Jour indisponible: {blocked_day.label}")

    overlap_query = db.query(Appointment).filter(
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    )
    if appointment_id_to_ignore is not None:
        overlap_query = overlap_query.filter(Appointment.id != appointment_id_to_ignore)
    if overlap_query.first():
        raise HTTPException(status_code=409, detail="Conflit detecte avec un autre rendez-vous.")


@router.get("/agenda", response_model=List[AppointmentResponse])
@router.get("/appointments", response_model=List[AppointmentResponse], include_in_schema=False)
async def list_appointments(db: Session = Depends(get_db)) -> List[AppointmentResponse]:
    appointments = db.query(Appointment).order_by(Appointment.start_time.asc()).all()
    return [AppointmentResponse.from_orm(a) for a in appointments]


@router.post("/agenda", response_model=AppointmentResponse, status_code=201)
@router.post("/appointments", response_model=AppointmentResponse, status_code=201, include_in_schema=False)
async def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)) -> AppointmentResponse:
    settings = _get_or_create_settings(db)
    _assert_appointment_allowed(db, settings, payload.start_time, payload.end_time)
    appointment = Appointment(
        customer_id=payload.customer_id,
        source_call_id=payload.source_call_id,
        entreprise_id=payload.entreprise_id,
        phone_number=payload.phone_number,
        title=payload.title,
        start_time=payload.start_time,
        end_time=payload.end_time,
        location=payload.location,
        status=payload.status,
        service_type=payload.service_type,
        agenda_tag=payload.agenda_tag,
        display_icon=payload.display_icon,
        display_color=payload.display_color,
        is_all_day=payload.is_all_day,
        notes=payload.notes,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    logger.info(f"RDV cree: {appointment.id} - {appointment.title}")
    return AppointmentResponse.from_orm(appointment)


@router.patch("/agenda/{appointment_id}", response_model=AppointmentResponse)
@router.patch("/appointments/{appointment_id}", response_model=AppointmentResponse, include_in_schema=False)
async def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
) -> AppointmentResponse:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable.")

    updates = payload.model_dump(exclude_unset=True)
    next_start = updates.get("start_time", appointment.start_time)
    next_end = updates.get("end_time", appointment.end_time)
    settings = _get_or_create_settings(db)
    _assert_appointment_allowed(db, settings, next_start, next_end, appointment_id_to_ignore=appointment_id)

    for key, value in updates.items():
        setattr(appointment, key, value)
    db.commit()
    db.refresh(appointment)
    return AppointmentResponse.from_orm(appointment)


@router.delete("/agenda/{appointment_id}", status_code=204)
@router.delete("/appointments/{appointment_id}", status_code=204, include_in_schema=False)
async def delete_appointment(appointment_id: int, db: Session = Depends(get_db)) -> None:
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable.")
    db.delete(appointment)
    db.commit()


@router.get("/agenda/settings", response_model=AppointmentSettingsResponse)
@router.get("/appointments/settings", response_model=AppointmentSettingsResponse, include_in_schema=False)
async def get_appointment_settings(db: Session = Depends(get_db)) -> AppointmentSettingsResponse:
    return AppointmentSettingsResponse.from_orm(_get_or_create_settings(db))


@router.put("/agenda/settings", response_model=AppointmentSettingsResponse)
@router.put("/appointments/settings", response_model=AppointmentSettingsResponse, include_in_schema=False)
async def update_appointment_settings(
    payload: AppointmentSettingsBase,
    db: Session = Depends(get_db),
) -> AppointmentSettingsResponse:
    if payload.work_day_end <= payload.work_day_start:
        raise HTTPException(status_code=400, detail="L'heure de fin doit etre strictement apres l'heure de debut.")
    settings = _get_or_create_settings(db)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return AppointmentSettingsResponse.from_orm(settings)


@router.get("/agenda/non-working-days", response_model=List[AppointmentNonWorkingDayResponse])
@router.get("/appointments/non-working-days", response_model=List[AppointmentNonWorkingDayResponse], include_in_schema=False)
async def list_non_working_days(db: Session = Depends(get_db)) -> List[AppointmentNonWorkingDayResponse]:
    days = db.query(AppointmentNonWorkingDay).order_by(AppointmentNonWorkingDay.date.asc()).all()
    return [AppointmentNonWorkingDayResponse.from_orm(day) for day in days]


@router.post("/agenda/non-working-days", response_model=AppointmentNonWorkingDayResponse, status_code=201)
@router.post("/appointments/non-working-days", response_model=AppointmentNonWorkingDayResponse, status_code=201, include_in_schema=False)
async def create_non_working_day(
    payload: AppointmentNonWorkingDayCreate,
    db: Session = Depends(get_db),
) -> AppointmentNonWorkingDayResponse:
    exists = db.query(AppointmentNonWorkingDay).filter(AppointmentNonWorkingDay.date == payload.date).first()
    if exists:
        raise HTTPException(status_code=409, detail="Ce jour existe deja.")
    day = AppointmentNonWorkingDay(date=payload.date, label=payload.label)
    db.add(day)
    db.commit()
    db.refresh(day)
    return AppointmentNonWorkingDayResponse.from_orm(day)


@router.delete("/agenda/non-working-days/{day_id}", status_code=204)
@router.delete("/appointments/non-working-days/{day_id}", status_code=204, include_in_schema=False)
async def delete_non_working_day(day_id: int, db: Session = Depends(get_db)) -> None:
    day = db.query(AppointmentNonWorkingDay).filter(AppointmentNonWorkingDay.id == day_id).first()
    if not day:
        raise HTTPException(status_code=404, detail="Jour non travaille introuvable.")
    db.delete(day)
    db.commit()


@router.get("/agenda/context")
@router.get("/appointments/context", include_in_schema=False)
async def get_appointments_context(db: Session = Depends(get_db)) -> dict:
    settings = _get_or_create_settings(db)
    non_working_days = (
        db.query(AppointmentNonWorkingDay).order_by(AppointmentNonWorkingDay.date.asc()).all()
    )
    recent_calls = db.query(Call).order_by(Call.call_time.desc()).limit(30).all()
    ml_brain = _get_ml_brain()
    call_suggestions = []
    for call in recent_calls:
        metadata = dict(call.extra_data or {})
        intent = metadata.get("ivr_intent")
        transcription = call.transcription or ""
        if intent or transcription:
            ml_context = None
            if ml_brain and transcription:
                try:
                    ml_context = ml_brain.build_context(transcription, top_k=3)
                except Exception:
                    ml_context = None

            call_suggestions.append(
                {
                    "call_id": call.id,
                    "phone_number": call.phone_number,
                    "call_time": call.call_time.isoformat() if call.call_time else None,
                    "intent": intent,
                    "transcription": transcription,
                    "ml_context": ml_context,
                }
            )

    return {
        "settings": AppointmentSettingsResponse.from_orm(settings).model_dump(),
        "non_working_days": [AppointmentNonWorkingDayResponse.from_orm(day).model_dump() for day in non_working_days],
        "appointment_count": db.query(Appointment).count(),
        "suggested_calls": call_suggestions,
        "ml_context_enabled": bool(ml_brain),
        "generated_at": datetime.utcnow().isoformat(),
    }

