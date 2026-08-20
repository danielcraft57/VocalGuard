"""
Route API pour les statistiques du dashboard.
Retourne les compteurs des cartes et les donnees reelles pour les graphiques.
"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from backend.api.models import DashboardStatsResponse, DailyStatsItem
from backend.database.database import get_db
from backend.database.models import Call, Appointment, Quote, PhoneNumberProfile, Voicemail


router = APIRouter()

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStatsResponse:
    """
    Retourne les compteurs pour le dashboard et les donnees pour les graphiques :
    - cartes : appels aujourd'hui, RDV, devis, suspects OSINT ;
    - graphiques : total_calls, total_blocked, daily_series (7 derniers jours).
    """
    today_start = datetime.combine(date.today(), time.min)
    today_end = today_start + timedelta(days=1)

    calls_today = (
        db.query(func.count(Call.id))
        .filter(Call.call_time >= today_start, Call.call_time < today_end)
        .scalar()
        or 0
    )

    rdv_count = db.query(func.count(Appointment.id)).scalar() or 0
    quotes_count = db.query(func.count(Quote.id)).scalar() or 0

    suspects_count = (
        db.query(func.count(PhoneNumberProfile.id))
        .filter(
            or_(
                PhoneNumberProfile.reputation == "low",
                PhoneNumberProfile.is_spam == True,
                PhoneNumberProfile.is_scam == True,
            )
        )
        .scalar()
        or 0
    )

    total_calls = db.query(func.count(Call.id)).scalar() or 0
    total_blocked = (
        db.query(func.count(Call.id)).filter(Call.status == "blocked").scalar() or 0
    )

    voicemails_today = (
        db.query(func.count(Voicemail.id))
        .filter(Voicemail.created_at >= today_start, Voicemail.created_at < today_end)
        .scalar()
        or 0
    )
    voicemails_unread = (
        db.query(func.count(Voicemail.id))
        .filter(Voicemail.is_read == False, Voicemail.is_archived == False)  # noqa: E712
        .scalar()
        or 0
    )
    voicemails_total = db.query(func.count(Voicemail.id)).scalar() or 0

    daily_series = _build_daily_series(db)

    return DashboardStatsResponse(
        calls_today=calls_today,
        rdv_count=rdv_count,
        quotes_count=quotes_count,
        suspects_count=suspects_count,
        total_calls=total_calls,
        total_blocked=total_blocked,
        voicemails_today=voicemails_today,
        voicemails_unread=voicemails_unread,
        voicemails_total=voicemails_total,
        daily_series=daily_series,
    )


def _build_daily_series(db: Session) -> list:
    """Construit les stats par jour pour les 7 derniers jours (ordre Lun -> Dim)."""
    result = []
    today = date.today()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        day_start = datetime.combine(d, time.min)
        day_end = day_start + timedelta(days=1)

        calls = (
            db.query(func.count(Call.id))
            .filter(Call.call_time >= day_start, Call.call_time < day_end)
            .scalar()
            or 0
        )
        rdv = (
            db.query(func.count(Appointment.id))
            .filter(Appointment.created_at >= day_start, Appointment.created_at < day_end)
            .scalar()
            or 0
        )
        quotes = (
            db.query(func.count(Quote.id))
            .filter(Quote.created_at >= day_start, Quote.created_at < day_end)
            .scalar()
            or 0
        )
        spam = (
            db.query(func.count(Call.id))
            .filter(
                Call.call_time >= day_start,
                Call.call_time < day_end,
                Call.status == "blocked",
            )
            .scalar()
            or 0
        )
        voicemails = (
            db.query(func.count(Voicemail.id))
            .filter(Voicemail.created_at >= day_start, Voicemail.created_at < day_end)
            .scalar()
            or 0
        )
        jour_label = JOURS[d.weekday()]
        result.append(
            DailyStatsItem(
                day=jour_label,
                date=d.isoformat(),
                calls=calls,
                rdv=rdv,
                quotes=quotes,
                spam=spam,
                voicemails=voicemails,
            )
        )
    return result
