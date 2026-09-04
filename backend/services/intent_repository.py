"""
Repository + seed + predict vectoriel pour intents KB.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from backend.database.models import Intent, IntentEmbedding, IntentPattern, IntentResponse
from backend.voice.intent_embed import (
    EMBED_DIM,
    cosine_similarity,
    embed_text,
    normalize_intent_text,
)

DEFAULT_SEED_PATH = Path("data/intents/kb_seed/conversation_v1.json")
_TAG_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")


def default_seed_path(base_path: Optional[Path] = None) -> Path:
    """
    Chemin du catalogue seed.

    @param base_path Racine projet.
    @returns Path JSON.
    """
    root = Path(base_path) if base_path else Path(".")
    return root / DEFAULT_SEED_PATH


def load_seed_catalog(path: Path) -> List[Dict[str, Any]]:
    """
    Charge le JSON de seed.

    @param path Fichier conversation_v1.json.
    @returns Liste d'intents dict.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents") or []
    if not isinstance(intents, list):
        raise ValueError("Seed invalide: 'intents' doit etre une liste")
    return intents


def _intent_to_dict(intent: Intent) -> Dict[str, Any]:
    """Serialise un intent ORM en dict API."""
    return {
        "id": intent.id,
        "tag": intent.tag,
        "source": intent.source,
        "niveau": intent.niveau,
        "enabled": intent.enabled,
        "priority": intent.priority,
        "wav_basename": intent.wav_basename,
        "action": intent.action,
        "patterns": [p.pattern for p in intent.patterns],
        "responses": [r.text for r in sorted(intent.responses, key=lambda x: x.position)],
    }


def seed_intents_from_catalog(
    db: Session,
    catalog: Sequence[Dict[str, Any]],
    *,
    source: str = "seed",
    replace: bool = False,
) -> int:
    """
    Importe le catalogue dans les tables normalisees + embeddings.

    @param db Session SQLAlchemy.
    @param catalog Liste d'intents seed.
    @param source Valeur colonne source.
    @param replace Si True, recree les lignes existantes (meme tag).
    @returns Nombre d'intents upsertes.
    """
    count = 0
    for item in catalog:
        tag = str(item.get("tag") or "").strip()
        if not tag:
            continue
        existing = db.query(Intent).filter(Intent.tag == tag).one_or_none()
        if existing and not replace:
            continue
        if existing and replace:
            db.delete(existing)
            db.flush()

        intent = Intent(
            tag=tag,
            source=str(item.get("source") or source),
            niveau=int(item.get("niveau") or 1),
            enabled=bool(item.get("enabled", True)),
            priority=int(item.get("priority") or 10),
            wav_basename=str(item.get("wav_basename") or f"kb_{tag}"),
            action=(str(item["action"]).strip() if item.get("action") else None),
        )
        db.add(intent)
        db.flush()

        patterns = item.get("patterns") or []
        for pattern in patterns:
            ptxt = str(pattern or "").strip()
            if not ptxt:
                continue
            row = IntentPattern(intent_id=intent.id, pattern=ptxt, weight=1.0)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "pattern", row.id, embed_text(ptxt))

        responses = item.get("responses") or []
        for pos, response in enumerate(responses):
            rtxt = str(response or "").strip()
            if not rtxt:
                continue
            row = IntentResponse(intent_id=intent.id, position=pos, text=rtxt)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "response", row.id, embed_text(rtxt))

        count += 1

    db.commit()
    _sync_pgvector_column(db)
    logger.info("Seed intents: {} upsertes (replace={})", count, replace)
    return count


def _upsert_embedding(
    db: Session,
    intent_id: int,
    ref_type: str,
    ref_id: int,
    vector: Sequence[float],
) -> None:
    """Cree ou met a jour un embedding JSON."""
    row = (
        db.query(IntentEmbedding)
        .filter(IntentEmbedding.ref_type == ref_type, IntentEmbedding.ref_id == ref_id)
        .one_or_none()
    )
    payload = [float(x) for x in vector]
    if row is None:
        db.add(
            IntentEmbedding(
                intent_id=intent_id,
                ref_type=ref_type,
                ref_id=ref_id,
                embedding_json=payload,
                dim=len(payload) or EMBED_DIM,
            )
        )
    else:
        row.intent_id = intent_id
        row.embedding_json = payload
        row.dim = len(payload) or EMBED_DIM


def _sync_pgvector_column(db: Session) -> None:
    """
    Synchronise la colonne ``embedding`` pgvector depuis ``embedding_json``.

    Ignore silencieusement si l'extension / colonne absente (SQLite, avant mig 004).
    """
    try:
        db.execute(
            text(
                """
                UPDATE intent_embeddings
                SET embedding = embedding_json::text::vector
                WHERE embedding_json IS NOT NULL
                """
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug("Sync pgvector ignoree: {}", exc)


def ensure_seeded(db: Session, base_path: Optional[Path] = None) -> int:
    """
    Seed les intents manquants + complete les variantes seed absentes.

    @param db Session.
    @param base_path Racine projet.
    @returns Nombre d'intents nouvellement inseres.
    """
    path = default_seed_path(base_path)
    if not path.is_file():
        logger.warning("Seed intents introuvable: {}", path)
        return 0
    catalog = load_seed_catalog(path)
    inserted = seed_intents_from_catalog(db, catalog, replace=False)
    _sync_missing_seed_variants(db, catalog)
    return inserted


def _sync_missing_seed_variants(db: Session, catalog: Sequence[Dict[str, Any]]) -> int:
    """
    Ajoute patterns/responses du seed absents (sans ecraser le custom).

    @param db Session.
    @param catalog Catalogue seed.
    @returns Nombre de textes ajoutes.
    """
    added = 0
    for item in catalog:
        tag = str(item.get("tag") or "").strip()
        if not tag:
            continue
        intent = get_intent_by_tag(db, tag)
        if intent is None:
            continue

        existing_patterns = {
            normalize_intent_text(p.pattern) for p in intent.patterns
        }
        for pattern in item.get("patterns") or []:
            ptxt = str(pattern or "").strip()
            if not ptxt:
                continue
            if normalize_intent_text(ptxt) in existing_patterns:
                continue
            row = IntentPattern(intent_id=intent.id, pattern=ptxt, weight=1.0)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "pattern", row.id, embed_text(ptxt))
            existing_patterns.add(normalize_intent_text(ptxt))
            added += 1

        existing_resp = {
            normalize_intent_text(r.text) for r in intent.responses
        }
        next_pos = max((r.position for r in intent.responses), default=-1) + 1
        for response in item.get("responses") or []:
            rtxt = str(response or "").strip()
            if not rtxt:
                continue
            if normalize_intent_text(rtxt) in existing_resp:
                continue
            row = IntentResponse(intent_id=intent.id, position=next_pos, text=rtxt)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "response", row.id, embed_text(rtxt))
            existing_resp.add(normalize_intent_text(rtxt))
            next_pos += 1
            added += 1

    if added:
        db.commit()
        _sync_pgvector_column(db)
        logger.info("Seed variants sync: {} textes ajoutes", added)
    return added


def list_intents_detailed(db: Session, *, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """
    Liste les intents avec patterns et responses.

    @param db Session.
    @param enabled_only Filtre enabled.
    @returns Liste de dicts API.
    """
    q = db.query(Intent).options(
        selectinload(Intent.patterns),
        selectinload(Intent.responses),
    )
    if enabled_only:
        q = q.filter(Intent.enabled.is_(True))
    rows = q.order_by(Intent.priority.desc(), Intent.tag.asc()).all()
    return [_intent_to_dict(intent) for intent in rows]


def get_intent_by_tag(db: Session, tag: str) -> Optional[Intent]:
    """Charge un intent par tag."""
    return (
        db.query(Intent)
        .options(selectinload(Intent.patterns), selectinload(Intent.responses))
        .filter(Intent.tag == tag)
        .one_or_none()
    )


def create_intent(
    db: Session,
    *,
    tag: str,
    patterns: Optional[List[str]] = None,
    responses: Optional[List[str]] = None,
    priority: int = 10,
    enabled: bool = True,
    action: Optional[str] = None,
    source: str = "kb",
    niveau: int = 1,
) -> Dict[str, Any]:
    """
    Cree un intent normalise + embeddings.

    @raises ValueError Si tag invalide ou deja pris.
    """
    clean = (tag or "").strip().lower()
    if not _TAG_RE.match(clean):
        raise ValueError("Tag invalide (a-z, 0-9, _, 2-80 car., commence par une lettre)")
    if get_intent_by_tag(db, clean) is not None:
        raise ValueError(f"Tag deja existant: {clean}")

    intent = Intent(
        tag=clean,
        source=source,
        niveau=int(niveau),
        enabled=bool(enabled),
        priority=int(priority),
        wav_basename=f"kb_{clean}",
        action=(action.strip() if action else None),
    )
    db.add(intent)
    db.flush()

    for ptxt in patterns or []:
        p = str(ptxt or "").strip()
        if not p:
            continue
        row = IntentPattern(intent_id=intent.id, pattern=p, weight=1.0)
        db.add(row)
        db.flush()
        _upsert_embedding(db, intent.id, "pattern", row.id, embed_text(p))

    for pos, rtxt in enumerate(responses or []):
        r = str(rtxt or "").strip()
        if not r:
            continue
        row = IntentResponse(intent_id=intent.id, position=pos, text=r)
        db.add(row)
        db.flush()
        _upsert_embedding(db, intent.id, "response", row.id, embed_text(r))

    db.commit()
    _sync_pgvector_column(db)
    created = get_intent_by_tag(db, clean)
    assert created is not None
    return _intent_to_dict(created)


def delete_intent(db: Session, tag: str) -> bool:
    """
    Supprime un intent (CASCADE patterns/responses/embeddings).

    @returns True si supprime.
    """
    intent = get_intent_by_tag(db, tag)
    if intent is None:
        return False
    db.delete(intent)
    db.commit()
    return True


def pattern_boost_scores(db: Session, text: str) -> Dict[str, float]:
    """
    Boost lexical si un pattern apparait dans le texte cumule.

    @param db Session.
    @param text Texte normalise ou brut.
    @returns tag -> bonus.
    """
    norm = normalize_intent_text(text)
    if not norm:
        return {}
    boosts: Dict[str, float] = {}
    rows = (
        db.query(IntentPattern, Intent)
        .join(Intent, Intent.id == IntentPattern.intent_id)
        .filter(Intent.enabled.is_(True))
        .all()
    )
    for pattern, intent in rows:
        p = normalize_intent_text(pattern.pattern)
        if p and p in norm:
            bonus = 0.08 * float(pattern.weight or 1.0)
            boosts[intent.tag] = boosts.get(intent.tag, 0.0) + bonus
    return boosts


def predict_intent_scores(
    db: Session,
    text: str,
    *,
    top_k: int = 8,
    use_pgvector: bool = True,
) -> List[Dict[str, Any]]:
    """
    Predict vector-first : embed + top-k, agreg par intent, boost patterns.

    @param db Session.
    @param text Texte cumule.
    @param top_k Nombre d'embeddings voisins.
    @param use_pgvector Tente SQL pgvector avant fallback Python.
    @returns Liste {tag, score} triee.
    """
    query = (text or "").strip()
    if not query:
        return []

    query_vec = embed_text(query)
    scored: Dict[str, float] = {}

    used_vector = False
    if use_pgvector:
        used_vector = _predict_pgvector(db, query_vec, scored, top_k=top_k)

    if not used_vector:
        _predict_python_cosine(db, query_vec, scored)

    boosts = pattern_boost_scores(db, query)
    for tag, bonus in boosts.items():
        scored[tag] = scored.get(tag, 0.0) + bonus

    items = [(t, max(0.0, s)) for t, s in scored.items()]
    items.sort(key=lambda kv: kv[1], reverse=True)
    total = sum(s for _, s in items) or 1.0
    return [{"tag": t, "score": float(s / total)} for t, s in items[: max(1, top_k)]]


def _predict_pgvector(
    db: Session,
    query_vec: Sequence[float],
    scored: Dict[str, float],
    *,
    top_k: int,
) -> bool:
    """
    Recherche HNSW cosine si colonne embedding presente.

    @returns True si la requete a fonctionne.
    """
    vec_lit = "[" + ",".join(f"{float(x):.8f}" for x in query_vec) + "]"
    try:
        rows = db.execute(
            text(
                """
                SELECT i.tag AS tag, 1 - (e.embedding <=> CAST(:q AS vector)) AS sim
                FROM intent_embeddings e
                JOIN intents i ON i.id = e.intent_id
                WHERE i.enabled = true AND e.embedding IS NOT NULL
                ORDER BY e.embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": vec_lit, "k": int(top_k) * 3},
        ).fetchall()
    except Exception as exc:
        db.rollback()
        logger.debug("pgvector predict fallback: {}", exc)
        return False

    if not rows:
        return False
    for tag, sim in rows:
        if tag is None:
            continue
        scored[str(tag)] = max(scored.get(str(tag), 0.0), float(sim or 0.0))
    return True


def _predict_python_cosine(
    db: Session,
    query_vec: Sequence[float],
    scored: Dict[str, float],
) -> None:
    """Fallback : cosine sur embedding_json en Python."""
    rows = (
        db.query(IntentEmbedding, Intent)
        .join(Intent, Intent.id == IntentEmbedding.intent_id)
        .filter(Intent.enabled.is_(True))
        .all()
    )
    for emb, intent in rows:
        vec = emb.embedding_json or []
        if not isinstance(vec, list) or not vec:
            continue
        sim = cosine_similarity(query_vec, vec)
        scored[intent.tag] = max(scored.get(intent.tag, 0.0), float(sim))


def update_intent_response(
    db: Session,
    tag: str,
    *,
    responses: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
    enabled: Optional[bool] = None,
    priority: Optional[int] = None,
    action: Optional[str] = None,
    clear_action: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Met a jour responses/patterns d'un intent et recalcule embeddings.

    @returns Dict detaille ou None si tag inconnu.
    """
    intent = get_intent_by_tag(db, tag)
    if intent is None:
        return None
    if enabled is not None:
        intent.enabled = bool(enabled)
    if priority is not None:
        intent.priority = int(priority)
    if clear_action:
        intent.action = None
    elif action is not None:
        intent.action = action.strip() or None

    if patterns is not None:
        for old in list(intent.patterns):
            db.query(IntentEmbedding).filter(
                IntentEmbedding.ref_type == "pattern",
                IntentEmbedding.ref_id == old.id,
            ).delete(synchronize_session=False)
            db.delete(old)
        db.flush()
        for ptxt in patterns:
            p = str(ptxt or "").strip()
            if not p:
                continue
            row = IntentPattern(intent_id=intent.id, pattern=p, weight=1.0)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "pattern", row.id, embed_text(p))

    if responses is not None:
        for old in list(intent.responses):
            db.query(IntentEmbedding).filter(
                IntentEmbedding.ref_type == "response",
                IntentEmbedding.ref_id == old.id,
            ).delete(synchronize_session=False)
            db.delete(old)
        db.flush()
        for pos, rtxt in enumerate(responses):
            r = str(rtxt or "").strip()
            if not r:
                continue
            row = IntentResponse(intent_id=intent.id, position=pos, text=r)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "response", row.id, embed_text(r))

    db.commit()
    _sync_pgvector_column(db)
    refreshed = get_intent_by_tag(db, tag)
    return _intent_to_dict(refreshed) if refreshed else None
