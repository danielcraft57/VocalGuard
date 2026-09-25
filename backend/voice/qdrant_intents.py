"""
Client leger Qdrant pour sync / recherche d'embeddings intents.

Utilise l'API HTTP (httpx). Active uniquement si ``QDRANT_URL`` est defini.

Collections :
- ``intents_inbound`` : appels entrants (KB conversation)
- ``intents_outbound_commercial`` : appel commercial sortant
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

import httpx
from loguru import logger

from backend.voice.intent_embed import EMBED_DIM

PROFILE_INBOUND = "inbound"
PROFILE_OUTBOUND_COMMERCIAL = "outbound_commercial"

COLLECTION_INBOUND = "intents_inbound"
COLLECTION_OUTBOUND_COMMERCIAL = "intents_outbound_commercial"
# Ancien nom (avant rename) - utilise pour migration / fallback.
LEGACY_COLLECTION = "intents"

DEFAULT_COLLECTION = COLLECTION_INBOUND

_PROFILE_TO_COLLECTION = {
    PROFILE_INBOUND: COLLECTION_INBOUND,
    PROFILE_OUTBOUND_COMMERCIAL: COLLECTION_OUTBOUND_COMMERCIAL,
}


def qdrant_base_url() -> Optional[str]:
    """
    URL de base Qdrant si activee.

    @returns URL sans slash final, ou None.
    """
    raw = (os.getenv("QDRANT_URL") or "").strip()
    if not raw:
        return None
    return raw.rstrip("/")


def collection_for_profile(profile: Optional[str] = None) -> str:
    """
    Nom de collection Qdrant pour un profil KB.

    @param profile ``inbound`` | ``outbound_commercial`` (defaut inbound).
    @returns Nom de collection.
    """
    key = (profile or PROFILE_INBOUND).strip().lower()
    return _PROFILE_TO_COLLECTION.get(key, COLLECTION_INBOUND)


def ensure_intents_collection(
    *,
    qdrant_url: Optional[str] = None,
    collection: str = DEFAULT_COLLECTION,
    dim: int = EMBED_DIM,
) -> bool:
    """
    Cree la collection intents si absente.

    @param qdrant_url Base URL (defaut env).
    @param collection Nom.
    @param dim Dimension vecteur.
    @returns True si collection OK.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base:
        return False
    info = f"{base}/collections/{collection}"
    try:
        with httpx.Client(timeout=10.0) as client:
            existing = client.get(info)
            if existing.status_code == 200:
                return True
            body = {
                "vectors": {"size": int(dim), "distance": "Cosine"},
                "optimizers_config": {"default_segment_number": 1},
            }
            created = client.put(info, json=body)
            if created.status_code not in (200, 201):
                logger.warning(
                    "Qdrant create collection HTTP {}: {}",
                    created.status_code,
                    created.text[:200],
                )
                return False
            return True
    except Exception as exc:
        logger.debug("Qdrant ensure collection ignoree: {}", exc)
        return False


def delete_collection(
    *,
    qdrant_url: Optional[str] = None,
    collection: str,
) -> bool:
    """
    Supprime une collection Qdrant (ex. apres migration ``intents`` -> inbound).

    @param qdrant_url Base URL.
    @param collection Nom a supprimer.
    @returns True si absente ou supprimee.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base or not collection:
        return False
    url = f"{base}/collections/{collection}"
    try:
        with httpx.Client(timeout=30.0) as client:
            existing = client.get(url)
            if existing.status_code == 404:
                return True
            deleted = client.delete(url)
            if deleted.status_code not in (200, 202):
                logger.warning(
                    "Qdrant delete collection HTTP {}: {}",
                    deleted.status_code,
                    deleted.text[:200],
                )
                return False
            return True
    except Exception as exc:
        logger.debug("Qdrant delete collection ignoree: {}", exc)
        return False


def resolve_search_collection(
    *,
    profile: Optional[str] = None,
    qdrant_url: Optional[str] = None,
) -> Optional[str]:
    """
    Collection a utiliser pour la recherche, avec fallback legacy ``intents``.

    @param profile Profil KB.
    @param qdrant_url Base URL.
    @returns Nom collection ou None si Qdrant injoignable / absente.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base:
        return None
    preferred = collection_for_profile(profile)
    try:
        with httpx.Client(timeout=2.0) as client:
            preferred_resp = client.get(f"{base}/collections/{preferred}")
            if preferred_resp.status_code == 200:
                return preferred
            # Fallback: ancienne collection uniquement pour inbound.
            if preferred == COLLECTION_INBOUND:
                legacy = client.get(f"{base}/collections/{LEGACY_COLLECTION}")
                if legacy.status_code == 200:
                    return LEGACY_COLLECTION
    except Exception as exc:
        logger.debug("Qdrant resolve collection ignoree: {}", exc)
    return preferred


def upsert_embedding_point(
    *,
    point_id: int,
    vector: Sequence[float],
    intent_tag: str,
    ref_type: str,
    ref_id: int,
    profile: Optional[str] = None,
    qdrant_url: Optional[str] = None,
    collection: Optional[str] = None,
) -> bool:
    """
    Upsert un point embedding dans Qdrant.

    @param point_id ID unique (souvent intent_embeddings.id).
    @param vector Vecteur dim EMBED_DIM.
    @param intent_tag Tag intent.
    @param ref_type pattern|response.
    @param ref_id ID pattern/response.
    @param profile Profil KB (choisit la collection si ``collection`` omis).
    @param collection Nom collection (prioritaire).
    @returns True si OK.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base:
        return False
    if len(vector) != EMBED_DIM:
        logger.debug("Qdrant upsert ignore: dim={} != {}", len(vector), EMBED_DIM)
        return False
    coll = collection or collection_for_profile(profile)
    ensure_intents_collection(qdrant_url=base, collection=coll)
    url = f"{base}/collections/{coll}/points?wait=true"
    prof = (profile or PROFILE_INBOUND).strip().lower()
    point: Dict[str, Any] = {
        "id": int(point_id),
        "vector": [float(x) for x in vector],
        "payload": {
            "intent_tag": str(intent_tag),
            "ref_type": str(ref_type),
            "ref_id": int(ref_id),
            "profile": prof,
        },
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.put(url, json={"points": [point]})
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.debug("Qdrant upsert ignore: {}", exc)
        return False


def fetch_qdrant_status(
    *,
    qdrant_url: Optional[str] = None,
    collection: str = DEFAULT_COLLECTION,
) -> Dict[str, Any]:
    """
    Snapshot sante Qdrant pour l'UI (health + compte points).

    @param qdrant_url Base URL (defaut env).
    @param collection Nom collection intents.
    @returns Dict configured/ok/url/points_count/detail.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base:
        return {
            "configured": False,
            "ok": False,
            "url": None,
            "collection": collection,
            "points_count": 0,
            "detail": "QDRANT_URL non configure",
        }
    try:
        with httpx.Client(timeout=2.0) as client:
            root = client.get(f"{base}/")
            if root.status_code != 200:
                return {
                    "configured": True,
                    "ok": False,
                    "url": base,
                    "collection": collection,
                    "points_count": 0,
                    "detail": f"HTTP {root.status_code}",
                }
            coll = client.get(f"{base}/collections/{collection}")
            points = 0
            if coll.status_code == 200:
                payload = coll.json() or {}
                result = payload.get("result") or {}
                points = int(result.get("points_count") or 0)
                return {
                    "configured": True,
                    "ok": True,
                    "url": base,
                    "collection": collection,
                    "points_count": points,
                    "detail": None,
                }
            # Fallback legacy pour inbound uniquement.
            if collection == COLLECTION_INBOUND:
                legacy = client.get(f"{base}/collections/{LEGACY_COLLECTION}")
                if legacy.status_code == 200:
                    payload = legacy.json() or {}
                    result = payload.get("result") or {}
                    points = int(result.get("points_count") or 0)
                    return {
                        "configured": True,
                        "ok": True,
                        "url": base,
                        "collection": LEGACY_COLLECTION,
                        "points_count": points,
                        "detail": "legacy collection intents (migrer vers intents_inbound)",
                    }
            return {
                "configured": True,
                "ok": False,
                "url": base,
                "collection": collection,
                "points_count": 0,
                "detail": f"collection HTTP {coll.status_code}",
            }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "url": base,
            "collection": collection,
            "points_count": 0,
            "detail": str(exc)[:160],
        }


def fetch_all_qdrant_status(
    *,
    qdrant_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Statut des deux collections (inbound + outbound commercial).

    @param qdrant_url Base URL.
    @returns Dict agrege + sous-cles par collection.
    """
    inbound = fetch_qdrant_status(
        qdrant_url=qdrant_url, collection=COLLECTION_INBOUND
    )
    outbound = fetch_qdrant_status(
        qdrant_url=qdrant_url, collection=COLLECTION_OUTBOUND_COMMERCIAL
    )
    configured = bool(inbound.get("configured") or outbound.get("configured"))
    ok = bool(inbound.get("ok") or outbound.get("ok"))
    return {
        "configured": configured,
        "ok": ok,
        "url": inbound.get("url") or outbound.get("url"),
        "inbound": inbound,
        "outbound_commercial": outbound,
        "qdrant_points_inbound": int(inbound.get("points_count") or 0),
        "qdrant_points_outbound": int(outbound.get("points_count") or 0),
        "detail": inbound.get("detail") if not inbound.get("ok") else outbound.get("detail"),
    }


def delete_points_by_ids(
    point_ids: List[int],
    *,
    qdrant_url: Optional[str] = None,
    collection: str = DEFAULT_COLLECTION,
    profile: Optional[str] = None,
) -> bool:
    """
    Supprime des points par ID.

    @param point_ids Liste d'IDs.
    @param collection Nom collection (prioritaire sur profile).
    @param profile Profil si collection omise.
    @returns True si OK.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base or not point_ids:
        return False
    coll = collection if collection else collection_for_profile(profile)
    url = f"{base}/collections/{coll}/points/delete?wait=true"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json={"points": [int(x) for x in point_ids]})
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.debug("Qdrant delete ignore: {}", exc)
        return False
