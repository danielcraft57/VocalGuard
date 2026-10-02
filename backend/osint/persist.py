"""
Persistance normalisee des resultats OSINT (sans JSON).

Met a jour `PhoneNumberProfile` + lignes `PhoneOsintSource`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.database.models import PhoneNumberProfile, PhoneOsintSource
from backend.osint_worker.reputation import is_plausible_spam_type


def _as_confidence_pct(value: Any) -> Optional[int]:
    """
    Convertit une confiance 0-1 ou 0-100 en entier 0-100.

    @param value Confiance brute.
    @returns Entier 0-100 ou None.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f <= 1.0:
        f = f * 100.0
    return max(0, min(100, int(round(f))))


def _normalize_source_codes(sources: Any) -> List[str]:
    """
    Deduplique et nettoie une liste de codes source.

    @param sources Liste ou iterable de codes.
    @returns Codes uniques non vides (max 32).
    """
    if not sources:
        return []
    out: List[str] = []
    seen = set()
    for item in sources:
        code = str(item or "").strip().lower()[:64]
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
        if len(out) >= 32:
            break
    return out


def apply_osint_result_to_profile(
    db: Session,
    profile: PhoneNumberProfile,
    result: Dict[str, Any],
    *,
    replace_sources: bool = True,
) -> None:
    """
    Recopie les champs scalaires OSINT vers le profil + table sources.

    Aucun dump JSON : uniquement colonnes typees.

    @param db Session SQLAlchemy.
    @param profile Profil a mettre a jour.
    @param result Dict enrichissement OSINT.
    @param replace_sources Si True, remplace les sources par le lot courant.
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
    profile.company_siren = result.get("company_siren") or profile.company_siren
    profile.company_siret = result.get("company_siret") or profile.company_siret
    profile.company_activity = result.get("company_activity") or profile.company_activity
    profile.company_address = result.get("company_address") or profile.company_address
    profile.is_company = bool(result.get("is_company") or profile.is_company)

    profile.reputation = result.get("reputation") or profile.reputation
    profile.is_spam = bool(result.get("is_spam") or profile.is_spam)
    profile.is_scam = bool(result.get("is_scam") or profile.is_scam)
    profile.is_commercial = bool(result.get("is_commercial") or profile.is_commercial)
    profile.is_telemarketer = bool(result.get("is_telemarketer") or profile.is_telemarketer)
    profile.is_robocall = bool(result.get("is_robocall") or profile.is_robocall)

    spam_type = result.get("spam_type")
    junk = {
        "image",
        "images",
        "img",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "webp",
        "icon",
        "logo",
        "button",
        "score",
        "scoreimage",
        "light",
        "dark",
        "none",
        "null",
    }
    if spam_type and is_plausible_spam_type(str(spam_type)):
        profile.spam_type = str(spam_type).strip()[:64]
    elif spam_type:
        # Artefact HTML (ex. data-type=image) : on efface l'ancien bruit
        profile.spam_type = None
    elif profile.spam_type and str(profile.spam_type).lower() in junk:
        profile.spam_type = None
    elif profile.spam_type and not is_plausible_spam_type(str(profile.spam_type)):
        profile.spam_type = None

    spam_score = result.get("spam_score")
    if spam_score is not None:
        try:
            profile.spam_score = float(spam_score)
        except (TypeError, ValueError):
            pass

    conf_pct = _as_confidence_pct(result.get("confidence"))
    if conf_pct is not None:
        profile.confidence = conf_pct

    profile.last_checked_at = datetime.utcnow()
    profile.updated_at = datetime.utcnow()

    sync_profile_sources(
        db,
        profile,
        result.get("sources") or [],
        replace=replace_sources,
    )


def sync_profile_sources(
    db: Session,
    profile: PhoneNumberProfile,
    sources: Iterable[Any],
    *,
    replace: bool = True,
) -> None:
    """
    Synchronise les lignes `phone_osint_sources` pour un profil.

    @param db Session.
    @param profile Profil cible (doit avoir un id).
    @param sources Codes source.
    @param replace Si True, supprime les anciennes lignes avant insert.
    """
    if profile.id is None:
        db.flush()

    codes = _normalize_source_codes(sources)
    now = datetime.utcnow()

    if replace:
        db.query(PhoneOsintSource).filter(PhoneOsintSource.profile_id == profile.id).delete(
            synchronize_session=False
        )
        for code in codes:
            db.add(
                PhoneOsintSource(
                    profile_id=profile.id,
                    source_code=code,
                    checked_at=now,
                )
            )
        return

    existing = {
        row.source_code
        for row in db.query(PhoneOsintSource.source_code)
        .filter(PhoneOsintSource.profile_id == profile.id)
        .all()
    }
    for code in codes:
        if code in existing:
            db.query(PhoneOsintSource).filter(
                PhoneOsintSource.profile_id == profile.id,
                PhoneOsintSource.source_code == code,
            ).update({"checked_at": now}, synchronize_session=False)
        else:
            db.add(
                PhoneOsintSource(
                    profile_id=profile.id,
                    source_code=code,
                    checked_at=now,
                )
            )


def source_codes_for_profile(profile: PhoneNumberProfile) -> List[str]:
    """
    Liste ordonnees des codes source d'un profil (relation chargee ou vide).

    @param profile Profil.
    @returns Codes source.
    """
    rows = getattr(profile, "osint_sources", None) or []
    return [r.source_code for r in rows if getattr(r, "source_code", None)]
