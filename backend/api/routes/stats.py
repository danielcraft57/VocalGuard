"""
Route API pour les statistiques du dashboard.
Compteurs + series 7 jours via peu de requetes SQL (group by).
"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, case, cast, Date

from backend.api.models import DashboardStatsResponse, DailyStatsItem
from backend.database.database import get_db
from backend.database.models import Call, Appointment, Quote, PhoneNumberProfile, Voicemail


router = APIRouter()

JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStatsResponse:
    """
    Retourne les compteurs dashboard et series 7 jours.

    Optimise Postgres : agrégats en peu de requetes (pas de boucle 35 COUNT).
    """
    today_start = datetime.combine(date.today(), time.min)
    today_end = today_start + timedelta(days=1)

    call_aggs = db.query(
        func.count(Call.id).label("total_calls"),
        func.count(case((Call.status == "blocked", 1))).label("total_blocked"),
        func.count(
            case(
                (
                    (Call.call_time >= today_start) & (Call.call_time < today_end),
                    1,
                )
            )
        ).label("calls_today"),
        func.count(
            case(
                (
                    (Call.call_time >= today_start)
                    & (Call.call_time < today_end)
                    & (Call.status == "blocked"),
                    1,
                )
            )
        ).label("blocked_today"),
    ).one()

    vm_aggs = db.query(
        func.count(Voicemail.id).label("voicemails_total"),
        func.count(
            case(
                (
                    (Voicemail.created_at >= today_start) & (Voicemail.created_at < today_end),
                    1,
                )
            )
        ).label("voicemails_today"),
        func.count(
            case(
                (
                    (Voicemail.is_read == False) & (Voicemail.is_archived == False),  # noqa: E712
                    1,
                )
            )
        ).label("voicemails_unread"),
    ).one()

    rdv_count = db.query(func.count(Appointment.id)).scalar() or 0
    quotes_count = db.query(func.count(Quote.id)).scalar() or 0
    suspects_count = (
        db.query(func.count(PhoneNumberProfile.id))
        .filter(
            or_(
                PhoneNumberProfile.reputation == "low",
                PhoneNumberProfile.is_spam == True,  # noqa: E712
                PhoneNumberProfile.is_scam == True,  # noqa: E712
            )
        )
        .scalar()
        or 0
    )

    daily_series = _build_daily_series(db)

    return DashboardStatsResponse(
        calls_today=int(call_aggs.calls_today or 0),
        rdv_count=rdv_count,
        quotes_count=quotes_count,
        suspects_count=suspects_count,
        total_calls=int(call_aggs.total_calls or 0),
        total_blocked=int(call_aggs.total_blocked or 0),
        blocked_today=int(call_aggs.blocked_today or 0),
        voicemails_today=int(vm_aggs.voicemails_today or 0),
        voicemails_unread=int(vm_aggs.voicemails_unread or 0),
        voicemails_total=int(vm_aggs.voicemails_total or 0),
        daily_series=daily_series,
    )


def _counts_by_day(rows) -> dict:
    """Mappe date -> count depuis un resultat group by."""
    out: dict = {}
    for day_val, cnt in rows:
        if day_val is None:
            continue
        if isinstance(day_val, datetime):
            key = day_val.date()
        elif isinstance(day_val, date):
            key = day_val
        else:
            key = day_val
        out[key] = int(cnt or 0)
    return out


def _build_daily_series(db: Session) -> list:
    """
    Stats par jour sur 7 jours via 5 GROUP BY (au lieu de 35 COUNT).

    @param db Session SQLAlchemy
    @returns Liste DailyStatsItem Lun->Dim relative aux 7 derniers jours
    """
    today = date.today()
    start = datetime.combine(today - timedelta(days=6), time.min)
    end = datetime.combine(today + timedelta(days=1), time.min)

    calls_map = _counts_by_day(
        db.query(cast(Call.call_time, Date), func.count(Call.id))
        .filter(Call.call_time >= start, Call.call_time < end)
        .group_by(cast(Call.call_time, Date))
        .all()
    )
    blocked_map = _counts_by_day(
        db.query(cast(Call.call_time, Date), func.count(Call.id))
        .filter(Call.call_time >= start, Call.call_time < end, Call.status == "blocked")
        .group_by(cast(Call.call_time, Date))
        .all()
    )
    rdv_map = _counts_by_day(
        db.query(cast(Appointment.created_at, Date), func.count(Appointment.id))
        .filter(Appointment.created_at >= start, Appointment.created_at < end)
        .group_by(cast(Appointment.created_at, Date))
        .all()
    )
    quotes_map = _counts_by_day(
        db.query(cast(Quote.created_at, Date), func.count(Quote.id))
        .filter(Quote.created_at >= start, Quote.created_at < end)
        .group_by(cast(Quote.created_at, Date))
        .all()
    )
    vm_map = _counts_by_day(
        db.query(cast(Voicemail.created_at, Date), func.count(Voicemail.id))
        .filter(Voicemail.created_at >= start, Voicemail.created_at < end)
        .group_by(cast(Voicemail.created_at, Date))
        .all()
    )

    result = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        result.append(
            DailyStatsItem(
                day=JOURS[d.weekday()],
                date=d.isoformat(),
                calls=calls_map.get(d, 0),
                rdv=rdv_map.get(d, 0),
                quotes=quotes_map.get(d, 0),
                spam=blocked_map.get(d, 0),
                voicemails=vm_map.get(d, 0),
            )
        )
    return result
