"""
Service de planification des rendez-vous.

Ce module ajoute une couche metier pour creer automatiquement un rendez-vous
depuis un appel vocal lorsqu'un intent de prise de rendez-vous est detecte.
"""

import re
from datetime import datetime, time, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.database.models import Appointment, AppointmentNonWorkingDay, AppointmentSettings


class AppointmentService:
    """Service metier agenda (CRUD metier + proposition de creneau)."""

    RDV_INTENT_NAMES = {"prise_rdv", "rendez_vous", "rendez-vous", "rdv"}
    WEEKDAY_MAP = {
        "lundi": 0,
        "mardi": 1,
        "mercredi": 2,
        "jeudi": 3,
        "vendredi": 4,
        "samedi": 5,
        "dimanche": 6,
    }

    def __init__(self, db: Session):
        """Initialise le service agenda."""
        self.db = db

    def get_or_create_settings(self) -> AppointmentSettings:
        """Retourne les parametres agenda, ou cree des valeurs par defaut."""
        settings = self.db.query(AppointmentSettings).order_by(AppointmentSettings.id.asc()).first()
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
        self.db.add(settings)
        self.db.commit()
        self.db.refresh(settings)
        return settings

    def maybe_schedule_from_intent(
        self,
        intent_name: Optional[str],
        transcription: str,
        call_id: Optional[int],
        phone_number: Optional[str],
    ) -> Optional[Appointment]:
        """
        Cree (ou met a jour) un rendez-vous automatiquement si l'intent correspond.

        - Evite les doublons avec `source_call_id`
        - Propose le prochain creneau disponible selon les regles agenda
        """
        if not self._is_rdv_intent(intent_name, transcription):
            return None

        if call_id:
            existing = self.db.query(Appointment).filter(Appointment.source_call_id == call_id).first()
            if existing:
                return existing

        preferred_start = self._extract_requested_start(transcription)
        slot = None
        if preferred_start is not None:
            slot = self._validate_specific_slot(preferred_start)
        if slot is None:
            slot = self._find_next_available_slot()
        if slot is None:
            return None

        start_time, end_time = slot
        appointment = Appointment(
            source_call_id=call_id,
            phone_number=phone_number,
            title="RDV a confirmer depuis appel vocal",
            start_time=start_time,
            end_time=end_time,
            status="pending_confirmation",
            notes=f"Creation automatique suite a intent vocal. Transcription: {transcription}",
        )
        self.db.add(appointment)
        self.db.commit()
        self.db.refresh(appointment)
        return appointment

    def _is_rdv_intent(self, intent_name: Optional[str], transcription: str) -> bool:
        """Determine si la phrase/intention correspond a une demande de rendez-vous."""
        if intent_name and intent_name.strip().lower() in self.RDV_INTENT_NAMES:
            return True
        text = (transcription or "").lower()
        return ("rendez" in text) or ("rdv" in text) or ("creneau" in text)

    def _find_next_available_slot(self) -> Optional[Tuple[datetime, datetime]]:
        """Calcule le prochain creneau libre en tenant compte des indisponibilites."""
        settings = self.get_or_create_settings()
        now = datetime.now()
        blocked_dates = {
            item.date
            for item in self.db.query(AppointmentNonWorkingDay).all()
        }
        slot_delta = timedelta(minutes=settings.slot_minutes)

        for day_offset in range(0, 21):
            day = now.date() + timedelta(days=day_offset)
            if day in blocked_dates:
                continue
            if not self._is_working_weekday(settings, day.weekday()):
                continue

            day_start = datetime.combine(day, settings.work_day_start)
            day_end = datetime.combine(day, settings.work_day_end)
            cursor = day_start
            if day == now.date() and cursor < now:
                minutes = settings.slot_minutes
                remainder = (now.minute % minutes)
                rounded = now.replace(second=0, microsecond=0)
                if remainder != 0:
                    rounded = rounded + timedelta(minutes=(minutes - remainder))
                cursor = max(day_start, rounded)

            while cursor + slot_delta <= day_end:
                candidate_start = cursor
                candidate_end = cursor + slot_delta
                overlap = self.db.query(Appointment).filter(
                    Appointment.start_time < candidate_end,
                    Appointment.end_time > candidate_start,
                ).first()
                if overlap is None:
                    return candidate_start, candidate_end
                cursor = cursor + slot_delta
        return None

    def _validate_specific_slot(self, requested_start: datetime) -> Optional[Tuple[datetime, datetime]]:
        """Valide un creneau demande dans la transcription, sinon retourne None."""
        settings = self.get_or_create_settings()
        requested_start = requested_start.replace(second=0, microsecond=0)
        if requested_start < datetime.now():
            return None
        slot_delta = timedelta(minutes=settings.slot_minutes)
        requested_end = requested_start + slot_delta
        blocked_dates = {
            item.date
            for item in self.db.query(AppointmentNonWorkingDay).all()
        }

        day = requested_start.date()
        if day in blocked_dates:
            return None
        if not self._is_working_weekday(settings, day.weekday()):
            return None
        if requested_start.time() < settings.work_day_start:
            return None
        if requested_end.time() > settings.work_day_end:
            return None

        overlap = self.db.query(Appointment).filter(
            Appointment.start_time < requested_end,
            Appointment.end_time > requested_start,
        ).first()
        if overlap is not None:
            return None
        return requested_start, requested_end

    def _extract_requested_start(self, transcription: str) -> Optional[datetime]:
        """
        Extrait un datetime simple depuis la phrase:
        - "demain a 14h" / "demain 14:30"
        - "vendredi a 10h30"
        """
        text = (transcription or "").lower()
        if not text:
            return None

        hour_match = re.search(r"(\d{1,2})(?:\s*h\s*|:)?(\d{2})?", text)
        if not hour_match:
            return None

        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
        if hour > 23 or minute > 59:
            return None

        now = datetime.now()
        target_date = None

        if "apres-demain" in text or "apres demain" in text:
            target_date = now.date() + timedelta(days=2)
        elif "demain" in text:
            target_date = now.date() + timedelta(days=1)
        else:
            for label, weekday in self.WEEKDAY_MAP.items():
                if label in text:
                    days_ahead = (weekday - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_date = now.date() + timedelta(days=days_ahead)
                    break

        if target_date is None:
            return None
        return datetime.combine(target_date, time(hour=hour, minute=minute))

    def _is_working_weekday(self, settings: AppointmentSettings, weekday: int) -> bool:
        """Vrai si le jour de semaine est autorise dans les reglages agenda."""
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
