"""
Moteur co-pilote appel commercial sortant (top-5 intents puis 5 phrases).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.services import intent_repository as intent_repo
from backend.voice.qdrant_intents import PROFILE_OUTBOUND_COMMERCIAL
from backend.voice.response_picker import variant_wav_basename


def _ivr_dir(config: Any) -> Path:
    """
    Dossier WAV modem.

    @param config Config app.
    @returns Path ``ivr_wav``.
    """
    base = Path(getattr(config, "base_path", None) or ".")
    return base / "ivr_wav"


def wav_ready(config: Any, basename: str) -> bool:
    """
    True si le fichier WAV modem existe et n'est pas vide.

    @param config Config.
    @param basename Sans extension.
    @returns Bool.
    """
    path = _ivr_dir(config) / f"{basename}.wav"
    try:
        return path.is_file() and path.stat().st_size > 200
    except OSError:
        return False


def build_phrase_choices(
    intent: Dict[str, Any],
    config: Any,
) -> List[Dict[str, Any]]:
    """
    Construit jusqu'a 5 formulations pour un intent.

    @param intent Dict detaille (responses, wav_basename, tag).
    @param config Config (chemins WAV).
    @returns Liste {rank, key, text, variant_index, wav_basename, wav_ready}.
    """
    tag = str(intent.get("tag") or "")
    custom = intent.get("wav_basename")
    responses = [
        str(r).strip() for r in (intent.get("responses") or []) if str(r).strip()
    ][:5]
    out: List[Dict[str, Any]] = []
    for idx, text in enumerate(responses):
        basename = variant_wav_basename(
            tag,
            idx,
            wav_basename=str(custom) if custom else None,
        )
        out.append(
            {
                "rank": idx + 1,
                "key": str(idx + 1),
                "text": text,
                "variant_index": idx,
                "wav_basename": basename,
                "wav_ready": wav_ready(config, basename),
            }
        )
    return out


def suggest_top_intents(
    db: Session,
    text: str,
    config: Any,
    *,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Predict top-k intents commerciaux + resume pour l'UI.

    @param db Session.
    @param text Texte STT / operateur.
    @param config Config.
    @param top_k Nombre d'intents (defaut 5).
    @returns Dict engine, suggestions, text.
    """
    preds, engine = intent_repo.predict_intent_scores_detailed(
        db,
        text,
        top_k=max(1, int(top_k)),
        profile=PROFILE_OUTBOUND_COMMERCIAL,
    )
    suggestions: List[Dict[str, Any]] = []
    for i, row in enumerate(preds[:5]):
        tag = str(row.get("tag") or "")
        intent = intent_repo.get_intent_by_tag(db, tag)
        if intent is None:
            continue
        detail = intent_repo._intent_to_dict(intent)
        responses = detail.get("responses") or []
        preview = str(responses[0]).strip() if responses else ""
        suggestions.append(
            {
                "rank": i + 1,
                "key": str(i + 1),
                "tag": tag,
                "score": float(row.get("score") or 0.0),
                "preview": preview,
                "action": detail.get("action"),
                "niveau": detail.get("niveau"),
                "phrases_count": len(responses),
                "wav_ready_any": any(
                    p["wav_ready"] for p in build_phrase_choices(detail, config)
                ),
            }
        )
    return {
        "text": (text or "").strip(),
        "engine": engine,
        "profile": PROFILE_OUTBOUND_COMMERCIAL,
        "suggestions": suggestions,
    }


def select_intent_phrases(
    db: Session,
    tag: str,
    config: Any,
) -> Dict[str, Any]:
    """
    Charge les 5 formulations d'un intent choisi.

    @param db Session.
    @param tag Tag intent.
    @param config Config.
    @returns Dict tag + phrases.
    @raises ValueError Si tag inconnu / mauvais profil.
    """
    intent = intent_repo.get_intent_by_tag(db, tag)
    if intent is None:
        raise ValueError(f"Intent inconnu: {tag}")
    detail = intent_repo._intent_to_dict(intent)
    if detail.get("profile") != PROFILE_OUTBOUND_COMMERCIAL:
        raise ValueError(f"Intent hors profil commercial: {tag}")
    phrases = build_phrase_choices(detail, config)
    return {
        "tag": tag,
        "action": detail.get("action"),
        "phrases": phrases,
    }


def resolve_choice(
    db: Session,
    config: Any,
    *,
    tag: str,
    variant_index: int,
) -> Dict[str, Any]:
    """
    Resout un choix final (tag + variante) vers texte + chemin WAV.

    @param db Session.
    @param config Config.
    @param tag Tag intent.
    @param variant_index Index 0..4.
    @returns Dict playable.
    @raises ValueError Si choix invalide ou WAV manquant.
    """
    payload = select_intent_phrases(db, tag, config)
    phrases = payload.get("phrases") or []
    idx = int(variant_index)
    if idx < 0 or idx >= len(phrases):
        raise ValueError(f"Variante invalide: {variant_index}")
    phrase = phrases[idx]
    basename = str(phrase["wav_basename"])
    path = _ivr_dir(config) / f"{basename}.wav"
    if not path.is_file() or path.stat().st_size < 200:
        logger.warning("WAV commercial manquant: {}", path)
        raise ValueError(
            f"Voix manquante pour {basename} - lancez la regeneration des voix sortantes"
        )
    return {
        "tag": tag,
        "variant_index": idx,
        "text": phrase["text"],
        "wav_basename": basename,
        "wav_path": str(path),
        "action": payload.get("action"),
        "wav_ready": True,
    }


def presentation_phrases(db: Session, config: Any) -> Dict[str, Any]:
    """
    Formulations d'ouverture (intent ``out_presentation``).

    @param db Session.
    @param config Config.
    @returns Phrases presentation.
    """
    return select_intent_phrases(db, "out_presentation", config)
