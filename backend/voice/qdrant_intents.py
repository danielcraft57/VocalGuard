"""
Client leger Qdrant pour sync / recherche d'embeddings intents.

Utilise l'API HTTP (httpx). Active uniquement si ``QDRANT_URL`` est defini.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

import httpx
from loguru import logger

from backend.voice.intent_embed import EMBED_DIM

DEFAULT_COLLECTION = "intents"


def qdrant_base_url() -> Optional[str]:
    """
    URL de base Qdrant si activee.

    @returns URL sans slash final, ou None.
    """
    raw = (os.getenv("QDRANT_URL") or "").strip()
    if not raw:
        return None
    return raw.rstrip("/")


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


def upsert_embedding_point(
    *,
    point_id: int,
    vector: Sequence[float],
    intent_tag: str,
    ref_type: str,
    ref_id: int,
    qdrant_url: Optional[str] = None,
    collection: str = DEFAULT_COLLECTION,
) -> bool:
    """
    Upsert un point embedding dans Qdrant.

    @param point_id ID unique (souvent intent_embeddings.id).
    @param vector Vecteur dim EMBED_DIM.
    @param intent_tag Tag intent.
    @param ref_type pattern|response.
    @param ref_id ID pattern/response.
    @returns True si OK.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base:
        return False
    if len(vector) != EMBED_DIM:
        logger.debug("Qdrant upsert ignore: dim={} != {}", len(vector), EMBED_DIM)
        return False
    ensure_intents_collection(qdrant_url=base, collection=collection)
    url = f"{base}/collections/{collection}/points?wait=true"
    point: Dict[str, Any] = {
        "id": int(point_id),
        "vector": [float(x) for x in vector],
        "payload": {
            "intent_tag": str(intent_tag),
            "ref_type": str(ref_type),
            "ref_id": int(ref_id),
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


def delete_points_by_ids(
    point_ids: List[int],
    *,
    qdrant_url: Optional[str] = None,
    collection: str = DEFAULT_COLLECTION,
) -> bool:
    """
    Supprime des points par ID.

    @param point_ids Liste d'IDs.
    @returns True si OK.
    """
    base = (qdrant_url or qdrant_base_url() or "").rstrip("/")
    if not base or not point_ids:
        return False
    url = f"{base}/collections/{collection}/points/delete?wait=true"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json={"points": [int(x) for x in point_ids]})
            response.raise_for_status()
            return True
    except Exception as exc:
        logger.debug("Qdrant delete ignore: {}", exc)
        return False
