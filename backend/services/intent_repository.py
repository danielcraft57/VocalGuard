"""
Repository + seed + predict vectoriel pour intents KB.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import httpx

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
from backend.voice.qdrant_intents import (
    PROFILE_INBOUND,
    PROFILE_OUTBOUND_COMMERCIAL,
    collection_for_profile,
    delete_points_by_ids,
    qdrant_base_url,
    resolve_search_collection,
    upsert_embedding_point,
)

DEFAULT_SEED_PATH = Path("data/intents/kb_seed/conversation_v1.json")
OUTBOUND_SEED_PATH = Path("data/intents/kb_seed/outbound_commercial_v1.json")
_TAG_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")

# Evite de recharger / rescanner les seeds JSON a chaque GET /kb/intents (~5s sinon).
_SEED_ENSURE_TTL_SEC = 120.0
_seed_ensure_last: Dict[str, float] = {}


def _seed_ensure_cache_key(profile: Optional[str]) -> str:
    """Cle memo pour ensure_seeded (tous profils ou un seul)."""
    return (profile or "*").strip().lower() or "*"


def invalidate_seed_ensure_cache() -> None:
    """Invalide le cache ensure_seeded (apres import / regen admin)."""
    _seed_ensure_last.clear()


def default_seed_path(base_path: Optional[Path] = None) -> Path:
    """
    Chemin du catalogue seed inbound (appels entrants).

    @param base_path Racine projet.
    @returns Path JSON.
    """
    root = Path(base_path) if base_path else Path(".")
    return root / DEFAULT_SEED_PATH


def outbound_seed_path(base_path: Optional[Path] = None) -> Path:
    """
    Chemin du catalogue seed commercial sortant.

    @param base_path Racine projet.
    @returns Path JSON.
    """
    root = Path(base_path) if base_path else Path(".")
    return root / OUTBOUND_SEED_PATH


def seed_path_for_profile(
    profile: Optional[str] = None,
    base_path: Optional[Path] = None,
) -> Path:
    """
    Seed JSON selon le profil KB.

    @param profile ``inbound`` | ``outbound_commercial``.
    @param base_path Racine projet.
    @returns Path fichier seed.
    """
    key = (profile or PROFILE_INBOUND).strip().lower()
    if key == PROFILE_OUTBOUND_COMMERCIAL:
        return outbound_seed_path(base_path)
    return default_seed_path(base_path)


def load_seed_catalog(path: Path) -> List[Dict[str, Any]]:
    """
    Charge le JSON de seed.

    @param path Fichier conversation_v1.json ou outbound_commercial_v1.json.
    @returns Liste d'intents dict.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    intents = payload.get("intents") or []
    if not isinstance(intents, list):
        raise ValueError("Seed invalide: 'intents' doit etre une liste")
    default_profile = str(payload.get("profile") or PROFILE_INBOUND).strip().lower()
    for item in intents:
        if isinstance(item, dict) and not item.get("profile"):
            item["profile"] = default_profile
    return intents


def _intent_to_dict(intent: Intent) -> Dict[str, Any]:
    """Serialise un intent ORM en dict API."""
    return {
        "id": intent.id,
        "tag": intent.tag,
        "profile": getattr(intent, "profile", None) or PROFILE_INBOUND,
        "source": intent.source,
        "niveau": intent.niveau,
        "enabled": intent.enabled,
        "priority": intent.priority,
        "wav_basename": intent.wav_basename,
        "action": intent.action,
        "patterns": [p.pattern for p in intent.patterns],
        "responses": [r.text for r in sorted(intent.responses, key=lambda x: x.position)],
    }


def _wav_prefix_for_profile(profile: str) -> str:
    """
    Prefixe basename WAV selon le profil.

    @param profile Profil KB.
    @returns ``kb`` ou ``out_kb``.
    """
    if (profile or "").strip().lower() == PROFILE_OUTBOUND_COMMERCIAL:
        return "out_kb"
    return "kb"


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
        profile = str(item.get("profile") or PROFILE_INBOUND).strip().lower()
        if profile not in (PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL):
            profile = PROFILE_INBOUND
        existing = db.query(Intent).filter(Intent.tag == tag).one_or_none()
        if existing and not replace:
            continue
        if existing and replace:
            db.delete(existing)
            db.flush()

        prefix = _wav_prefix_for_profile(profile)
        intent = Intent(
            tag=tag,
            profile=profile,
            source=str(item.get("source") or source),
            niveau=int(item.get("niveau") or 1),
            enabled=bool(item.get("enabled", True)),
            priority=int(item.get("priority") or 10),
            wav_basename=str(item.get("wav_basename") or f"{prefix}_{tag}"),
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
    """
    Cree ou met a jour un embedding JSON (+ sync Qdrant si configure).

    @param db Session SQLAlchemy.
    @param intent_id ID intent parent.
    @param ref_type pattern|response.
    @param ref_id ID de la ligne pattern/response.
    @param vector Vecteur float.
    """
    row = (
        db.query(IntentEmbedding)
        .filter(IntentEmbedding.ref_type == ref_type, IntentEmbedding.ref_id == ref_id)
        .one_or_none()
    )
    payload = [float(x) for x in vector]
    if row is None:
        row = IntentEmbedding(
            intent_id=intent_id,
            ref_type=ref_type,
            ref_id=ref_id,
            embedding_json=payload,
            dim=len(payload) or EMBED_DIM,
        )
        db.add(row)
        db.flush()
    else:
        row.intent_id = intent_id
        row.embedding_json = payload
        row.dim = len(payload) or EMBED_DIM
        db.flush()

    if qdrant_base_url() and row.id is not None:
        intent = db.query(Intent).filter(Intent.id == intent_id).one_or_none()
        tag = intent.tag if intent is not None else ""
        profile = (
            getattr(intent, "profile", None) if intent is not None else None
        ) or PROFILE_INBOUND
        upsert_embedding_point(
            point_id=int(row.id),
            vector=payload,
            intent_tag=tag,
            ref_type=ref_type,
            ref_id=ref_id,
            profile=profile,
            collection=collection_for_profile(profile),
        )


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


def ensure_seeded(
    db: Session,
    base_path: Optional[Path] = None,
    *,
    profile: Optional[str] = None,
    force: bool = False,
) -> int:
    """
    Seed les intents manquants + complete les variantes seed absentes.

    Sans ``profile`` : seed inbound puis outbound_commercial.
    Memoize ~2 min pour ne pas ralentir chaque GET UI.

    @param db Session.
    @param base_path Racine projet.
    @param profile Profil unique optionnel.
    @param force Ignore le cache TTL.
    @returns Nombre d'intents nouvellement inseres.
    """
    cache_key = _seed_ensure_cache_key(profile)
    now = time.monotonic()
    if not force:
        last = _seed_ensure_last.get(cache_key, 0.0)
        if now - last < _SEED_ENSURE_TTL_SEC:
            return 0

    profiles = (
        [profile]
        if profile
        else [PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL]
    )
    total = 0
    for prof in profiles:
        path = seed_path_for_profile(prof, base_path)
        if not path.is_file():
            logger.warning("Seed intents introuvable: {} ({})", path, prof)
            continue
        catalog = load_seed_catalog(path)
        inserted = seed_intents_from_catalog(db, catalog, replace=False)
        _sync_missing_seed_variants(db, catalog)
        total += inserted
    _seed_ensure_last[cache_key] = time.monotonic()
    return total


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


def list_intents_detailed(
    db: Session,
    *,
    enabled_only: bool = False,
    profile: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Liste les intents avec patterns et responses.

    @param db Session.
    @param enabled_only Filtre enabled.
    @param profile Filtre profil (None = tous).
    @returns Liste de dicts API.
    """
    q = db.query(Intent).options(
        selectinload(Intent.patterns),
        selectinload(Intent.responses),
    )
    if enabled_only:
        q = q.filter(Intent.enabled.is_(True))
    if profile:
        q = q.filter(Intent.profile == profile.strip().lower())
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
    profile: str = PROFILE_INBOUND,
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

    prof = (profile or PROFILE_INBOUND).strip().lower()
    if prof not in (PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL):
        prof = PROFILE_INBOUND
    prefix = _wav_prefix_for_profile(prof)
    intent = Intent(
        tag=clean,
        profile=prof,
        source=source,
        niveau=int(niveau),
        enabled=bool(enabled),
        priority=int(priority),
        wav_basename=f"{prefix}_{clean}",
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


def _collect_embedding_ids(
    db: Session,
    ref_type: str,
    ref_ids: Sequence[int],
) -> List[int]:
    """
    Recupere les IDs intent_embeddings pour une liste de ref.

    @param db Session.
    @param ref_type pattern|response.
    @param ref_ids IDs pattern/response.
    @returns Liste d'IDs embedding.
    """
    clean = [int(x) for x in ref_ids if x is not None]
    if not clean:
        return []
    rows = (
        db.query(IntentEmbedding.id)
        .filter(
            IntentEmbedding.ref_type == ref_type,
            IntentEmbedding.ref_id.in_(clean),
        )
        .all()
    )
    return [int(r[0]) for r in rows if r[0] is not None]


def delete_intent(db: Session, tag: str) -> bool:
    """
    Supprime un intent (CASCADE patterns/responses/embeddings + Qdrant).

    @param db Session SQLAlchemy.
    @param tag Tag intent.
    @returns True si supprime.
    """
    intent = get_intent_by_tag(db, tag)
    if intent is None:
        return False
    emb_ids = [
        int(r[0])
        for r in db.query(IntentEmbedding.id)
        .filter(IntentEmbedding.intent_id == intent.id)
        .all()
        if r[0] is not None
    ]
    profile = getattr(intent, "profile", None) or PROFILE_INBOUND
    db.delete(intent)
    db.commit()
    if emb_ids and qdrant_base_url():
        delete_points_by_ids(
            emb_ids,
            collection=collection_for_profile(profile),
            profile=profile,
        )
    return True


def delete_intents_by_profile(db: Session, profile: str) -> int:
    """
    Supprime tous les intents d'un profil (CASCADE + Qdrant).

    @param db Session.
    @param profile ``inbound`` | ``outbound_commercial``.
    @returns Nombre d'intents supprimes.
    """
    prof = (profile or PROFILE_INBOUND).strip().lower()
    if prof not in (PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL):
        raise ValueError(f"Profil invalide: {profile}")

    rows = db.query(Intent).filter(Intent.profile == prof).all()
    if not rows:
        _seed_ensure_last.pop(_seed_ensure_cache_key(prof), None)
        _seed_ensure_last.pop(_seed_ensure_cache_key(None), None)
        return 0

    emb_ids: List[int] = []
    tags: List[str] = []
    for intent in rows:
        tags.append(intent.tag)
        emb_ids.extend(
            int(r[0])
            for r in db.query(IntentEmbedding.id)
            .filter(IntentEmbedding.intent_id == intent.id)
            .all()
            if r[0] is not None
        )
        db.delete(intent)

    db.commit()
    if emb_ids and qdrant_base_url():
        delete_points_by_ids(
            emb_ids,
            collection=collection_for_profile(prof),
            profile=prof,
        )

    _seed_ensure_last.pop(_seed_ensure_cache_key(prof), None)
    _seed_ensure_last.pop(_seed_ensure_cache_key(None), None)
    logger.info("Wipe intents profile={}: {} tags", prof, len(tags))
    return len(tags)


def _qdrant_base_url() -> Optional[str]:
    """
    URL de base Qdrant si activee (env QDRANT_URL).

    @returns URL sans slash final, ou None si desactive.
    """
    return qdrant_base_url()


def _predict_qdrant(
    db: Session,
    query_vec: Sequence[float],
    scored: Dict[str, float],
    *,
    top_k: int,
    profile: Optional[str] = None,
) -> bool:
    """
    Recherche via Qdrant HTTP API (collection selon profil).

    Active uniquement si ``QDRANT_URL`` est defini (pas de tentative
    silencieuse sur localhost pour eviter une latence inutile).

    @param db Session (inutilisee ici, signature alignee).
    @param query_vec Vecteur requete L2-normalise.
    @param scored Dict tag -> score a remplir.
    @param top_k Nombre de voisins demandes.
    @param profile ``inbound`` | ``outbound_commercial``.
    @returns True si la requete a retourne des resultats utilisables.
    """
    qdrant_url = _qdrant_base_url()
    if not qdrant_url:
        return False
    collection = resolve_search_collection(profile=profile, qdrant_url=qdrant_url)
    if not collection:
        return False
    url = f"{qdrant_url}/collections/{collection}/points/search"
    body = {
        "vector": [float(x) for x in query_vec],
        "limit": int(top_k) * 4,
        "with_payload": True,
    }
    try:
        resp = httpx.post(url, json=body, timeout=2.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("result") or data.get("points") or data.get("data") or []
        if not items:
            return False
        want_profile = (profile or PROFILE_INBOUND).strip().lower()
        for item in items:
            payload = item.get("payload") or {}
            tag = payload.get("intent_tag")
            ref_type = payload.get("ref_type")
            point_profile = str(payload.get("profile") or want_profile).strip().lower()
            # Ignore les points d'un autre profil si le payload est renseigne.
            if payload.get("profile") and point_profile != want_profile:
                continue
            score = float(item.get("score") or 0.0)
            if not tag:
                continue
            weight = 1.0 if str(ref_type or "") == "pattern" else 0.35
            val = float(score) * weight
            scored[str(tag)] = max(scored.get(str(tag), 0.0), val)
        return bool(scored)
    except Exception as exc:
        logger.debug("qdrant predict fallback: {}", exc)
        return False


def pattern_boost_scores(
    db: Session,
    text: str,
    *,
    profile: Optional[str] = None,
) -> Dict[str, float]:
    """
    Boost lexical si un pattern apparait dans le texte cumule.

    @param db Session.
    @param text Texte normalise ou brut.
    @param profile Filtre profil optionnel.
    @returns tag -> bonus.
    """
    norm = normalize_intent_text(text)
    if not norm:
        return {}
    boosts: Dict[str, float] = {}
    q = (
        db.query(IntentPattern, Intent)
        .join(Intent, Intent.id == IntentPattern.intent_id)
        .filter(Intent.enabled.is_(True))
    )
    if profile:
        q = q.filter(Intent.profile == profile.strip().lower())
    rows = q.all()
    for pattern, intent in rows:
        p = normalize_intent_text(pattern.pattern)
        if not p:
            continue
        # Sous-chaine stricte OU tous les tokens du pattern presents (ordre libre).
        hit = p in norm
        if not hit:
            toks = [t for t in p.split() if len(t) > 2]
            hit = bool(toks) and all(t in norm for t in toks)
        if hit:
            bonus = 0.12 * float(pattern.weight or 1.0)
            # Patterns longs = plus discriminants.
            if len(p) >= 18:
                bonus += 0.06
            boosts[intent.tag] = boosts.get(intent.tag, 0.0) + bonus
    return boosts


def predict_intent_scores_detailed(
    db: Session,
    text: str,
    *,
    top_k: int = 8,
    use_pgvector: bool = True,
    profile: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """
    Predict vector-first + nom du moteur utilise.

    @param db Session.
    @param text Texte cumule.
    @param top_k Nombre d'embeddings voisins.
    @param use_pgvector Tente SQL pgvector avant fallback Python.
    @param profile Catalogue KB (defaut inbound).
    @returns (liste {tag, score}, engine) engine in
             qdrant|pgvector|python|empty.
    """
    query = (text or "").strip()
    if not query:
        return [], "empty"

    prof = (profile or PROFILE_INBOUND).strip().lower()
    query_vec = embed_text(query)
    scored: Dict[str, float] = {}
    engine = "python"

    used_qdrant = False
    try:
        used_qdrant = _predict_qdrant(
            db, query_vec, scored, top_k=top_k, profile=prof
        )
    except Exception:
        used_qdrant = False
    if used_qdrant:
        engine = "qdrant"
    elif use_pgvector and _predict_pgvector(
        db, query_vec, scored, top_k=top_k, profile=prof
    ):
        engine = "pgvector"
    else:
        _predict_python_cosine(db, query_vec, scored, profile=prof)
        engine = "python"

    boosts = pattern_boost_scores(db, query, profile=prof)
    for tag, bonus in boosts.items():
        scored[tag] = scored.get(tag, 0.0) + bonus

    items = [(t, max(0.0, s)) for t, s in scored.items()]
    items.sort(key=lambda kv: kv[1], reverse=True)
    total = sum(s for _, s in items) or 1.0
    preds = [{"tag": t, "score": float(s / total)} for t, s in items[: max(1, top_k)]]
    return preds, engine


def predict_intent_scores(
    db: Session,
    text: str,
    *,
    top_k: int = 8,
    use_pgvector: bool = True,
    profile: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Predict vector-first : embed + top-k, agreg par intent, boost patterns.

    @param db Session.
    @param text Texte cumule.
    @param top_k Nombre d'embeddings voisins.
    @param use_pgvector Tente SQL pgvector avant fallback Python.
    @param profile Catalogue KB.
    @returns Liste {tag, score} triee.
    """
    preds, _engine = predict_intent_scores_detailed(
        db, text, top_k=top_k, use_pgvector=use_pgvector, profile=profile
    )
    return preds


def _predict_pgvector(
    db: Session,
    query_vec: Sequence[float],
    scored: Dict[str, float],
    *,
    top_k: int,
    profile: Optional[str] = None,
) -> bool:
    """
    Recherche HNSW cosine si colonne embedding presente.

    Les embeddings ``pattern`` pesent plus que ``response`` : les reponses
    (ex. \"laissez vos coordonnees\") ne doivent pas detourner la predication.

    @returns True si la requete a fonctionne.
    """
    vec_lit = "[" + ",".join(f"{float(x):.8f}" for x in query_vec) + "]"
    prof = (profile or PROFILE_INBOUND).strip().lower()
    try:
        rows = db.execute(
            text(
                """
                SELECT i.tag AS tag, e.ref_type AS ref_type,
                       1 - (e.embedding <=> CAST(:q AS vector)) AS sim
                FROM intent_embeddings e
                JOIN intents i ON i.id = e.intent_id
                WHERE i.enabled = true
                  AND i.profile = :profile
                  AND e.embedding IS NOT NULL
                ORDER BY e.embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": vec_lit, "k": int(top_k) * 4, "profile": prof},
        ).fetchall()
    except Exception as exc:
        db.rollback()
        logger.debug("pgvector predict fallback: {}", exc)
        return False

    if not rows:
        return False
    for tag, ref_type, sim in rows:
        if tag is None:
            continue
        weight = 1.0 if str(ref_type or "") == "pattern" else 0.35
        val = float(sim or 0.0) * weight
        scored[str(tag)] = max(scored.get(str(tag), 0.0), val)
    return True


def _predict_python_cosine(
    db: Session,
    query_vec: Sequence[float],
    scored: Dict[str, float],
    *,
    profile: Optional[str] = None,
) -> None:
    """Fallback : cosine sur embedding_json en Python (patterns > responses)."""
    q = (
        db.query(IntentEmbedding, Intent)
        .join(Intent, Intent.id == IntentEmbedding.intent_id)
        .filter(Intent.enabled.is_(True))
    )
    if profile:
        q = q.filter(Intent.profile == profile.strip().lower())
    rows = q.all()
    for emb, intent in rows:
        vec = emb.embedding_json or []
        if not isinstance(vec, list) or not vec:
            continue
        sim = cosine_similarity(query_vec, vec)
        weight = 1.0 if str(emb.ref_type or "") == "pattern" else 0.35
        scored[intent.tag] = max(scored.get(intent.tag, 0.0), float(sim) * weight)


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
        old_ids = _collect_embedding_ids(db, "pattern", [p.id for p in intent.patterns])
        for old in list(intent.patterns):
            db.query(IntentEmbedding).filter(
                IntentEmbedding.ref_type == "pattern",
                IntentEmbedding.ref_id == old.id,
            ).delete(synchronize_session=False)
            db.delete(old)
        db.flush()
        if old_ids and qdrant_base_url():
            delete_points_by_ids(
                old_ids,
                collection=collection_for_profile(
                    getattr(intent, "profile", None) or PROFILE_INBOUND
                ),
            )
        for ptxt in patterns:
            p = str(ptxt or "").strip()
            if not p:
                continue
            row = IntentPattern(intent_id=intent.id, pattern=p, weight=1.0)
            db.add(row)
            db.flush()
            _upsert_embedding(db, intent.id, "pattern", row.id, embed_text(p))

    if responses is not None:
        old_ids = _collect_embedding_ids(db, "response", [r.id for r in intent.responses])
        for old in list(intent.responses):
            db.query(IntentEmbedding).filter(
                IntentEmbedding.ref_type == "response",
                IntentEmbedding.ref_id == old.id,
            ).delete(synchronize_session=False)
            db.delete(old)
        db.flush()
        if old_ids and qdrant_base_url():
            delete_points_by_ids(
                old_ids,
                collection=collection_for_profile(
                    getattr(intent, "profile", None) or PROFILE_INBOUND
                ),
            )
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
