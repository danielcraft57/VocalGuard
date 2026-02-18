#!/usr/bin/env python3
"""
Migration des donnees de callattendant.db vers vocalguard.db.

Tables source (callattendant):
  - CallLog   -> calls + callers (numeros uniques)
  - Blacklist -> callers (is_blocked=True)
  - Whitelist -> callers (is_whitelisted=True)
  - Message   -> voicemails (avec call_id mappe depuis CallLog)

Avec --run-osint : apres migration, enrichit chaque numero migre via OSINT
et persiste les profils (phone_number_profiles) pour afficher la reputation
sans appels API au chargement de la page Appels.

A lancer depuis la racine du projet VocalGuard :
  python scripts/migrate_callattendant_to_vocalguard.py
  python scripts/migrate_callattendant_to_vocalguard.py --run-osint
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Ajouter la racine du projet au path pour importer backend
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from loguru import logger

from backend.database.models import Base, Caller, Call, Voicemail, PhoneNumberProfile


def parse_datetime(s: str | None) -> datetime | None:
    """Parse une date/heure callattendant (ex: 2022-09-15 13:11:06)."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%d-%b %I:%M %p"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Fallback: essayer d'extraire au moins la date
    try:
        return datetime.fromisoformat(s.replace(" ", "T", 1))
    except ValueError:
        return None


def map_action_to_status(action: str | None) -> str:
    """Map CallLog.Action vers Call.status."""
    if not action:
        return "completed"
    a = (action or "").strip().lower()
    if a == "blocked":
        return "blocked"
    if a in ("permitted", "screened", "answered"):
        return "completed"
    return "completed"


def normalize_phone(number: str | None) -> str:
    """Retourne un numero normalise (chiffres uniquement) ou chaine vide."""
    if not number:
        return ""
    return re.sub(r"\D", "", str(number).strip()) or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration callattendant.db -> vocalguard.db")
    parser.add_argument(
        "--source",
        default=str(PROJECT_ROOT / "callattendant.db"),
        help="Chemin vers callattendant.db",
    )
    parser.add_argument(
        "--target",
        default=str(PROJECT_ROOT / "vocalguard.db"),
        help="Chemin vers vocalguard.db",
    )
    parser.add_argument("--dry-run", action="store_true", help="Ne pas ecrire dans la cible")
    parser.add_argument(
        "--run-osint",
        action="store_true",
        help="Apres migration, lancer les analyses OSINT sur les numeros migres et persister les profils",
    )
    args = parser.parse_args()

    source_path = Path(args.source)
    target_path = Path(args.target)

    if not source_path.exists():
        logger.error("Fichier source introuvable: {}", source_path)
        return 1
    if not args.dry_run and not target_path.parent.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Source: {}", source_path)
    logger.info("Cible:  {} (dry_run={})", target_path, args.dry_run)

    # --- Lire callattendant ---
    conn_src = sqlite3.connect(str(source_path))
    conn_src.row_factory = sqlite3.Row

    blacklist = [dict(row) for row in conn_src.execute("SELECT * FROM Blacklist").fetchall()]
    whitelist = [dict(row) for row in conn_src.execute("SELECT * FROM Whitelist").fetchall()]
    call_logs = [
        dict(row)
        for row in conn_src.execute(
            "SELECT CallLogID, Name, Number, Action, Reason, Date, Time, SystemDateTime FROM CallLog ORDER BY CallLogID"
        ).fetchall()
    ]
    messages = [dict(row) for row in conn_src.execute("SELECT * FROM Message ORDER BY MessageID").fetchall()]

    conn_src.close()

    logger.info("Lu: {} blacklist, {} whitelist, {} appels, {} messages", len(blacklist), len(whitelist), len(call_logs), len(messages))

    if args.dry_run:
        logger.info("Dry-run: aucune ecriture.")
        return 0

    # --- Cible VocalGuard (SQLAlchemy) ---
    engine = create_engine(f"sqlite:///{target_path}", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    try:
        # 1) Callers existants (phone -> id) pour eviter doublons
        existing_phones: dict[str, int] = {}
        for c in session.query(Caller).all():
            existing_phones[normalize_phone(c.phone_number)] = c.id

        def get_or_create_caller(
            phone_number: str,
            name: str | None = None,
            is_blocked: bool = False,
            is_whitelisted: bool = False,
            notes: str | None = None,
        ) -> int:
            key = normalize_phone(phone_number)
            if not key:
                key = "_unknown_"
                phone_number = "inconnu"
            if key in existing_phones:
                caller = session.get(Caller, existing_phones[key])
                if caller:
                    if is_blocked:
                        caller.is_blocked = True
                    if is_whitelisted:
                        caller.is_whitelisted = True
                    if name and not caller.name:
                        caller.name = name[:255] if name else None
                    if notes and not caller.notes:
                        caller.notes = notes
                    session.flush()
                return existing_phones[key]
            caller = Caller(
                phone_number=(phone_number or "inconnu")[:20],
                name=(name or None)[:255] if name else None,
                is_blocked=is_blocked,
                is_whitelisted=is_whitelisted,
                notes=notes,
            )
            session.add(caller)
            session.flush()
            existing_phones[key] = caller.id
            return caller.id

        # 2) Whitelist -> callers
        for row in whitelist:
            phone = (row.get("PhoneNo") or "").strip()
            if not phone or not re.search(r"\d", phone):
                continue
            name_val = row.get("Name")
            name = (name_val.strip() if name_val and str(name_val).strip() != phone else None) or None
            reason = row.get("Reason")
            get_or_create_caller(
                phone_number=phone,
                name=name,
                is_blocked=False,
                is_whitelisted=True,
                notes=reason,
            )
        logger.info("Whitelist -> callers ok")

        # 3) Blacklist -> callers (is_blocked=True)
        for row in blacklist:
            phone = (row.get("PhoneNo") or "").strip()
            if not phone or not re.search(r"\d", phone):
                continue
            name_val = row.get("Name")
            name = (name_val.strip() if name_val and str(name_val).strip() != phone else None) or None
            reason = row.get("Reason")
            get_or_create_caller(
                phone_number=phone,
                name=name,
                is_blocked=True,
                is_whitelisted=False,
                notes=reason,
            )
        logger.info("Blacklist -> callers ok")

        # 4) CallLog -> callers (numeros pas encore vus) + calls
        old_calllog_id_to_new_call_id: dict[int, int] = {}
        for row in call_logs:
            calllog_id = row.get("CallLogID")
            number = (row.get("Number") or "").strip() or (row.get("Name") or "").strip()
            name_val = row.get("Name")
            name = (name_val.strip() if name_val and str(name_val).strip() != number else None) or None
            action = row.get("Action")
            reason = row.get("Reason")
            sys_dt = row.get("SystemDateTime")
            call_time = parse_datetime(sys_dt) if sys_dt else datetime.utcnow()

            if not number or not re.search(r"\d", number):
                number = "inconnu"

            caller_id = get_or_create_caller(phone_number=number, name=name)

            call = Call(
                caller_id=caller_id,
                phone_number=number[:20] if number else None,
                caller_name=(name or None)[:255] if name else None,
                call_time=call_time,
                status=map_action_to_status(action),
                extra_data={"migrated_from": "callattendant", "reason": reason} if reason else None,
            )
            session.add(call)
            session.flush()
            if calllog_id is not None:
                old_calllog_id_to_new_call_id[int(calllog_id)] = call.id

        logger.info("CallLog -> calls ok ({} entrées)", len(old_calllog_id_to_new_call_id))

        # 5) Message -> voicemails (call_id mappe)
        for row in messages:
            calllog_id = row.get("CallLogID")
            new_call_id = old_calllog_id_to_new_call_id.get(calllog_id) if calllog_id is not None else None
            filename = (row.get("Filename") or "").strip()
            if not filename:
                continue
            played = row.get("Played")
            dt = row.get("DateTime")
            created = parse_datetime(dt) if dt else datetime.utcnow()

            voicemail = Voicemail(
                call_id=new_call_id,
                audio_file=filename[:500],
                is_read=bool(played),
                created_at=created,
            )
            session.add(voicemail)

        logger.info("Message -> voicemails ok")
        session.commit()
        logger.info("Migration terminee avec succes.")

        if args.run_osint:
            logger.info("Lancement des analyses OSINT sur les numeros migres...")
            run_osint_count = run_osint_for_migrated_phones(target_path)
            logger.info("OSINT: {} numeros enrichis.", run_osint_count)

        return 0

    except Exception as e:
        logger.exception("Erreur migration: {}", e)
        session.rollback()
        return 1
    finally:
        session.close()


def _apply_osint_result_to_profile(profile: PhoneNumberProfile, result: Dict[str, Any]) -> None:
    """
    Recopie les champs utiles du resultat OSINT vers le profil.
    La reputation est remplie par le service OSINT : 'high'/'low' si une API externe
    (NumLookup, phoneinfoga) ou le detecteur commercial le fournit, sinon 'neutral'
    quand on a au moins lieu/operateur (detection FR), pour afficher "Non evaluee" en UI.
    """
    profile.country = result.get("country") or profile.country
    profile.region = result.get("region") or profile.region
    profile.city = result.get("city") or profile.city
    profile.department = result.get("department") or profile.department
    profile.postal_code = result.get("postal_code") or profile.postal_code
    profile.line_type = result.get("line_type") or profile.line_type
    profile.operator = result.get("operator") or profile.operator
    profile.carrier = result.get("carrier") or profile.carrier
    profile.name = result.get("name") or profile.name
    profile.company_name = result.get("company_name") or profile.company_name
    profile.is_company = bool(result.get("is_company") or profile.is_company)
    profile.reputation = result.get("reputation") or profile.reputation
    profile.is_spam = bool(result.get("is_spam") or profile.is_spam)
    profile.is_scam = bool(result.get("is_scam") or profile.is_scam)
    profile.is_commercial = bool(result.get("is_commercial") or profile.is_commercial)
    profile.is_telemarketer = bool(result.get("is_telemarketer") or profile.is_telemarketer)
    confidence: Optional[float] = result.get("confidence")
    if confidence is not None:
        profile.confidence = int(confidence * 100)
    profile.raw_data = result
    profile.last_checked_at = datetime.utcnow()


def run_osint_for_migrated_phones(target_path: Path) -> int:
    """
    Enrichit via OSINT chaque numero present dans les appels de la DB cible
    et persiste les profils dans phone_number_profiles.
    """
    from backend.core.config import Config
    from backend.services.osint_service import OSINTService

    engine = create_engine(f"sqlite:///{target_path}", echo=False)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    config = Config()
    osint_service = OSINTService(config)

    rows = session.query(Call.phone_number).distinct().all()
    phones = [r[0] for r in rows if r[0] and re.search(r"\d", str(r[0]))]
    count = 0

    for i, phone in enumerate(phones):
        try:
            normalized = normalize_phone(phone) or phone
            profile = (
                session.query(PhoneNumberProfile)
                .filter(PhoneNumberProfile.phone_number == phone)
                .order_by(desc(PhoneNumberProfile.last_checked_at))
                .first()
            )
            if not profile:
                profile = PhoneNumberProfile(
                    phone_number=phone[:32],
                    normalized_number=normalized[:32],
                )
                session.add(profile)
                session.flush()

            result = asyncio.run(osint_service.enrich_phone_number(phone))
            if isinstance(result, dict):
                _apply_osint_result_to_profile(profile, result)
                session.commit()
                count += 1
                if (i + 1) % 10 == 0:
                    logger.info("OSINT: {}/{} numeros traites.", i + 1, len(phones))
        except Exception as e:
            logger.warning("OSINT echoue pour {}: {}", phone, e)
            session.rollback()

    session.close()
    return count


if __name__ == "__main__":
    sys.exit(main())
