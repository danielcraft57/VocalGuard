"""API publique securisee par token pour RDV et entreprises."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.api.models import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    EntrepriseCreate,
    EntrepriseResponse,
    EntrepriseUpdate,
    PublicAgendaBookingCreate,
    ClientCreate,
    ClientResponse,
    QuoteCreate,
    QuoteResponse,
)
from backend.api.routes import appointments as appointments_routes
from backend.api.routes.entreprises import _to_entreprise_response, _attach_entreprise_emails
from backend.database.database import get_db
from backend.database.models import ApiPublicToken, Appointment, Entreprise, EntrepriseEmail, Client, Quote, Call

router = APIRouter(prefix="/public", tags=["public-api"])


def _extract_token(authorization: Optional[str], x_api_token: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_api_token:
        return x_api_token.strip()
    return None


def _require_public_token(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None),
) -> ApiPublicToken:
    token_value = _extract_token(authorization, x_api_token)
    if not token_value:
        raise HTTPException(status_code=401, detail="Token API public requis.")
    token = (
        db.query(ApiPublicToken)
        .filter(ApiPublicToken.token == token_value, ApiPublicToken.is_active.is_(True))
        .first()
    )
    if not token:
        raise HTTPException(status_code=401, detail="Token API public invalide.")
    token.last_used_at = datetime.utcnow()
    db.commit()
    return token


def _require_token_permission(token: ApiPublicToken, field: str, message: str) -> None:
    if not bool(getattr(token, field, False)):
        raise HTTPException(status_code=403, detail=message)


def _digits(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits or None


def _upsert_entreprise_from_public_payload(
    db: Session,
    *,
    contact_name: Optional[str],
    company_name: Optional[str],
    website: Optional[str],
    city: Optional[str],
    country: Optional[str],
    address_1: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    emails: Optional[List[str]],
) -> Optional[Entreprise]:
    """
    Trouve une entreprise existante et la met a jour, sinon en cree une.
    Regles de recherche:
    - 1) email exact (table normalisee entreprise_emails)
    - 2) telephone normalise (phone_digits)
    - 3) nom exact (fallback basique)
    """
    merged_emails_input = list(emails or [])
    if email:
        merged_emails_input.append(email)
    normalized_emails = sorted(
        {
            (x or "").strip().lower()
            for x in merged_emails_input
            if (x or "").strip() and "@" in (x or "")
        }
    )
    normalized_email = normalized_emails[0] if normalized_emails else None
    phone_digits = _digits(phone)
    preferred_name = (company_name or "").strip() or (contact_name or "").strip() or None
    website_clean = (website or "").strip() or None
    city_clean = (city or "").strip() or None
    country_clean = (country or "").strip() or None
    address_1_clean = (address_1 or "").strip() or None
    entreprise = None

    if normalized_email:
        entreprise = (
            db.query(Entreprise)
            .join(Entreprise.emails)
            .filter(EntrepriseEmail.email == normalized_email)
            .order_by(Entreprise.updated_at.desc())
            .first()
        )

    if not entreprise and phone_digits:
        entreprise = (
            db.query(Entreprise)
            .filter(Entreprise.phone_digits == phone_digits)
            .order_by(Entreprise.updated_at.desc())
            .first()
        )

    if not entreprise and preferred_name:
        entreprise = (
            db.query(Entreprise)
            .filter(Entreprise.name.ilike(preferred_name))  # type: ignore[attr-defined]
            .order_by(Entreprise.updated_at.desc())
            .first()
        )

    if not entreprise and website_clean:
        entreprise = (
            db.query(Entreprise)
            .filter(Entreprise.website.ilike(website_clean))  # type: ignore[attr-defined]
            .order_by(Entreprise.updated_at.desc())
            .first()
        )

    if not entreprise:
        entreprise = Entreprise(
            name=preferred_name or "Entreprise formulaire public",
            phone_number=phone,
            phone_digits=phone_digits,
            website=website_clean,
            city=city_clean,
            country=country_clean,
            address_1=address_1_clean,
        )
        db.add(entreprise)
        db.flush()

    if preferred_name and (not entreprise.name or entreprise.name == "Entreprise formulaire public"):
        entreprise.name = preferred_name
    if phone:
        entreprise.phone_number = phone
        entreprise.phone_digits = phone_digits
    if website_clean:
        entreprise.website = website_clean
    if city_clean:
        entreprise.city = city_clean
    if country_clean:
        entreprise.country = country_clean
    if address_1_clean:
        entreprise.address_1 = address_1_clean
    if normalized_email:
        existing_emails = sorted([(x.email or "").strip() for x in (entreprise.emails or []) if (x.email or "").strip()])
        merged = sorted(set(existing_emails + normalized_emails))
        _attach_entreprise_emails(db, entreprise, merged)

    return entreprise


@router.get("/agenda", response_model=List[AppointmentResponse])
@router.get("/appointments", response_model=List[AppointmentResponse], include_in_schema=False)
async def public_list_agenda(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> List[AppointmentResponse]:
    _require_token_permission(token, "can_read_agenda", "Ce token ne peut pas lire l'agenda.")
    rows = db.query(Appointment).order_by(Appointment.start_time.asc()).all()
    return [AppointmentResponse.from_orm(x) for x in rows]


@router.post("/agenda", response_model=AppointmentResponse, status_code=201)
@router.post("/appointments", response_model=AppointmentResponse, status_code=201, include_in_schema=False)
async def public_create_agenda(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> AppointmentResponse:
    _require_token_permission(token, "can_write_agenda", "Ce token ne peut pas modifier l'agenda.")
    return await appointments_routes.create_appointment(payload, db)


@router.patch("/agenda/{appointment_id}", response_model=AppointmentResponse)
@router.patch("/appointments/{appointment_id}", response_model=AppointmentResponse, include_in_schema=False)
async def public_update_agenda(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> AppointmentResponse:
    _require_token_permission(token, "can_write_agenda", "Ce token ne peut pas modifier l'agenda.")
    return await appointments_routes.update_appointment(appointment_id, payload, db)


@router.delete("/agenda/{appointment_id}", status_code=204)
@router.delete("/appointments/{appointment_id}", status_code=204, include_in_schema=False)
async def public_delete_agenda(
    appointment_id: int,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> Response:
    _require_token_permission(token, "can_write_agenda", "Ce token ne peut pas modifier l'agenda.")
    await appointments_routes.delete_appointment(appointment_id, db)
    return Response(status_code=204)


@router.post("/agenda/booking", response_model=AppointmentResponse, status_code=201)
async def public_create_agenda_booking(
    payload: PublicAgendaBookingCreate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> AppointmentResponse:
    _require_token_permission(token, "can_write_agenda", "Ce token ne peut pas modifier l'agenda.")
    start_time = datetime.fromisoformat(f"{payload.preferred_date.isoformat()}T{payload.preferred_time}:00")
    end_time = start_time + timedelta(hours=1)
    title_parts = ["RDV site"]
    if payload.name:
        title_parts.append(payload.name)
    if payload.service:
        title_parts.append(payload.service)
    title = " - ".join(title_parts)
    notes_lines = []
    if payload.message:
        notes_lines.append(payload.message.strip())
    if payload.project_type:
        notes_lines.append(f"project_type: {payload.project_type}")
    if payload.budget:
        notes_lines.append(f"budget: {payload.budget}")
    if payload.email:
        notes_lines.append(f"email: {payload.email}")
    if payload.emails:
        notes_lines.append(f"emails: {', '.join(payload.emails)}")
    if payload.company_name:
        notes_lines.append(f"company_name: {payload.company_name}")
    if payload.website:
        notes_lines.append(f"website: {payload.website}")
    if payload.city:
        notes_lines.append(f"city: {payload.city}")
    if payload.country:
        notes_lines.append(f"country: {payload.country}")
    if payload.address_1:
        notes_lines.append(f"address_1: {payload.address_1}")
    entreprise = _upsert_entreprise_from_public_payload(
        db,
        contact_name=payload.name,
        company_name=payload.company_name,
        website=payload.website,
        city=payload.city,
        country=payload.country,
        address_1=payload.address_1,
        phone=payload.phone,
        email=payload.email,
        emails=payload.emails,
    )
    create_payload = AppointmentCreate(
        entreprise_id=entreprise.id if entreprise else None,
        phone_number=payload.phone,
        title=title,
        start_time=start_time,
        end_time=end_time,
        service_type=payload.service,
        notes="\n".join([x for x in notes_lines if x]),
    )
    return await appointments_routes.create_appointment(create_payload, db)


@router.get("/availability/work-days")
async def get_work_days(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    _require_token_permission(token, "can_read_agenda", "Ce token ne peut pas lire l'agenda.")
    settings = appointments_routes._get_or_create_settings(db)
    return {
        "timezone": settings.timezone,
        "work_day_start": settings.work_day_start.isoformat(),
        "work_day_end": settings.work_day_end.isoformat(),
        "enabled_days": {
            "monday": settings.monday_enabled,
            "tuesday": settings.tuesday_enabled,
            "wednesday": settings.wednesday_enabled,
            "thursday": settings.thursday_enabled,
            "friday": settings.friday_enabled,
            "saturday": settings.saturday_enabled,
            "sunday": settings.sunday_enabled,
        },
    }


@router.get("/availability/slots")
async def get_available_slots(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    _require_token_permission(token, "can_read_agenda", "Ce token ne peut pas lire l'agenda.")
    if to_date < from_date:
        raise HTTPException(status_code=400, detail="to_date doit etre superieur ou egal a from_date.")
    settings = appointments_routes._get_or_create_settings(db)
    if (to_date - from_date).days > 60:
        raise HTTPException(status_code=400, detail="Periode trop grande (60 jours max).")

    non_working_days = {
        x.date for x in db.query(appointments_routes.AppointmentNonWorkingDay).filter(
            appointments_routes.AppointmentNonWorkingDay.date >= from_date,
            appointments_routes.AppointmentNonWorkingDay.date <= to_date,
        )
    }
    appointments = db.query(Appointment).filter(
        Appointment.start_time >= datetime.combine(from_date, settings.work_day_start),
        Appointment.start_time < datetime.combine(to_date + timedelta(days=1), settings.work_day_start),
    ).all()
    slots = []
    current = from_date
    slot_delta = timedelta(minutes=settings.slot_minutes)
    while current <= to_date:
        if (
            appointments_routes._is_enabled_weekday(settings, current.weekday())
            and current not in non_working_days
        ):
            start_at = datetime.combine(current, settings.work_day_start)
            end_limit = datetime.combine(current, settings.work_day_end)
            while start_at + slot_delta <= end_limit:
                candidate_end = start_at + slot_delta
                has_overlap = any(
                    a.start_time < candidate_end and a.end_time > start_at
                    for a in appointments
                )
                if not has_overlap:
                    slots.append(
                        {
                            "date": current.isoformat(),
                            "start_time": start_at.isoformat(),
                            "end_time": candidate_end.isoformat(),
                        }
                    )
                start_at = candidate_end
        current = current + timedelta(days=1)
    return {"count": len(slots), "slots": slots}


@router.post("/entreprises", response_model=EntrepriseResponse, status_code=201)
async def public_create_entreprise(
    payload: EntrepriseCreate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> EntrepriseResponse:
    _require_token_permission(token, "can_write_entreprises", "Ce token ne peut pas modifier les entreprises.")
    data = payload.model_dump()
    emails = data.pop("emails", [])
    entreprise = Entreprise(**data)
    db.add(entreprise)
    _attach_entreprise_emails(db, entreprise, emails)
    db.commit()
    db.refresh(entreprise)
    return _to_entreprise_response(entreprise)


@router.patch("/entreprises/{entreprise_id}", response_model=EntrepriseResponse)
async def public_update_entreprise(
    entreprise_id: int,
    payload: EntrepriseUpdate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> EntrepriseResponse:
    _require_token_permission(token, "can_write_entreprises", "Ce token ne peut pas modifier les entreprises.")
    entreprise = db.get(Entreprise, entreprise_id)  # type: ignore[arg-type]
    if not entreprise:
        raise HTTPException(status_code=404, detail="Entreprise introuvable")
    updates = payload.model_dump(exclude_unset=True)
    emails = updates.pop("emails", None)
    for key, value in updates.items():
        setattr(entreprise, key, value)
    if emails is not None:
        _attach_entreprise_emails(db, entreprise, emails)
    db.commit()
    db.refresh(entreprise)
    return _to_entreprise_response(entreprise)


@router.get("/clients", response_model=List[ClientResponse])
async def public_list_clients(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> List[ClientResponse]:
    _require_token_permission(token, "can_read_customers", "Ce token ne peut pas lire les clients.")
    rows = db.query(Client).order_by(Client.created_at.desc()).all()
    return [ClientResponse.from_orm(c) for c in rows]


@router.post("/clients", response_model=ClientResponse, status_code=201)
async def public_create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> ClientResponse:
    _require_token_permission(token, "can_write_customers", "Ce token ne peut pas modifier les clients.")
    client = Client(
        entreprise_id=getattr(payload, "entreprise_id", None),
        phone_number=payload.phone_number,
        email=payload.email,
        name=payload.name,
        notes=payload.notes,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return ClientResponse.from_orm(client)


@router.get("/quotes", response_model=List[QuoteResponse])
async def public_list_quotes(
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> List[QuoteResponse]:
    _require_token_permission(token, "can_read_quotes", "Ce token ne peut pas lire les devis.")
    quotes = db.query(Quote).order_by(Quote.created_at.desc()).all()
    return [QuoteResponse.from_orm(q) for q in quotes]


@router.post("/quotes", response_model=QuoteResponse, status_code=201)
async def public_create_quote(
    payload: QuoteCreate,
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> QuoteResponse:
    _require_token_permission(token, "can_write_quotes", "Ce token ne peut pas modifier les devis.")
    total_ht_float = sum(line.quantity * line.unit_price for line in payload.lines)
    total_ht = int(round(total_ht_float * 100))
    quote = Quote(
        client_id=payload.client_id,
        phone_number=payload.phone_number,
        title=payload.title,
        lines=[line.model_dump() for line in payload.lines],
        notes=payload.notes,
        status=payload.status,
        total_ht=total_ht,
        total_ttc=total_ht,
        created_at=datetime.utcnow(),
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return QuoteResponse.from_orm(quote)


@router.get("/calls")
async def public_list_calls(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    token: ApiPublicToken = Depends(_require_public_token),
) -> dict:
    _require_token_permission(token, "can_read_calls", "Ce token ne peut pas lire les appels.")
    total = db.query(func.count(Call.id)).scalar() or 0
    rows = (
        db.query(Call)
        .order_by(Call.call_time.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    out = []
    for c in rows:
        out.append(
            {
                "id": c.id,
                "phone_number": c.phone_number,
                "caller_name": c.caller_name,
                "call_time": c.call_time.isoformat() if c.call_time else None,
                "status": c.status,
                "duration": c.duration,
            }
        )
    return {"total": int(total), "skip": int(skip), "limit": int(limit), "calls": out}
