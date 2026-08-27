"""
Planning repondeur / telephone (config YAML, sans UI).

Si ``incoming_line_schedule.enabled`` est true, le mode du creneau courant
ecrase temporairement ``incoming_auto_answer`` pour l'appel en cours.
Le switch UI reste la source hors creneau.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Literal, Optional

from loguru import logger

LineMode = Literal["voicemail", "phone"]


def _parse_hhmm(value: str) -> Optional[time]:
    """Parse ``HH:MM`` ; None si invalide."""
    try:
        parts = str(value).strip().split(":")
        if len(parts) != 2:
            return None
        return time(hour=int(parts[0]), minute=int(parts[1]))
    except (TypeError, ValueError):
        return None


def _in_window(now_t: time, start: time, end: time) -> bool:
    """True si ``now_t`` est dans [start, end), avec support fenetre nuit (start > end)."""
    if start == end:
        return True
    if start < end:
        return start <= now_t < end
    # ex. 22:00 -> 07:00
    return now_t >= start or now_t < end


def resolve_scheduled_line_mode(
    schedule: Any,
    *,
    now: Optional[datetime] = None,
) -> Optional[LineMode]:
    """
    Retourne le mode force par le planning, ou None si desactive / hors creneau.

    Forme YAML attendue::

        incoming_line_schedule:
          enabled: true
          rules:
            - days: [0, 1, 2, 3, 4]  # lundi=0 ... dimanche=6
              start: "22:00"
              end: "07:00"
              mode: voicemail

    @param schedule Dict ou objet config.
    @param now Horloge (tests).
    @returns ``voicemail`` / ``phone`` ou None.
    """
    if not isinstance(schedule, dict):
        return None
    if not schedule.get("enabled"):
        return None
    rules = schedule.get("rules") or []
    if not isinstance(rules, list) or not rules:
        return None

    clock = now or datetime.now()
    weekday = clock.weekday()  # lundi=0
    now_t = clock.time().replace(second=0, microsecond=0)

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        mode = str(rule.get("mode") or "").strip().lower()
        if mode not in ("voicemail", "phone"):
            continue
        days = rule.get("days")
        if days is not None:
            try:
                day_set = {int(d) for d in days}
            except (TypeError, ValueError):
                continue
            if weekday not in day_set:
                continue
        start = _parse_hhmm(str(rule.get("start") or "00:00"))
        end = _parse_hhmm(str(rule.get("end") or "23:59"))
        if start is None or end is None:
            continue
        if _in_window(now_t, start, end):
            logger.info(
                "Planning ligne: mode {} (regle {}-{}, jour {})",
                mode,
                rule.get("start"),
                rule.get("end"),
                weekday,
            )
            return mode  # type: ignore[return-value]
    return None


def apply_schedule_to_auto_answer(config: Any, *, now: Optional[datetime] = None) -> bool:
    """
    Calcule ``incoming_auto_answer`` effectif (planning > switch UI).

    @param config Objet Config.
    @param now Horloge (tests).
    @returns True = repondeur modem (ATA).
    """
    schedule = getattr(config, "incoming_line_schedule", None)
    mode = resolve_scheduled_line_mode(schedule, now=now)
    if mode == "voicemail":
        return True
    if mode == "phone":
        return False
    return bool(getattr(config, "incoming_auto_answer", True))
