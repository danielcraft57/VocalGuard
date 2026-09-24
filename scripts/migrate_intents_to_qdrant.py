#!/usr/bin/env python3
"""
Migre les embeddings d'intents depuis Postgres (intent_embeddings)
vers une collection Qdrant.

Usage:
  export DATABASE_URL=postgresql+psycopg2://user:pass@node14.lan:5432/vocalguard
  export QDRANT_URL=http://127.0.0.1:6333
  python scripts/migrate_intents_to_qdrant.py

Cree la collection ``intents`` (dim 384, Cosine) si absente, puis upsert en batch.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.database import database as db_module
from backend.voice.intent_embed import EMBED_DIM


def ensure_db(database_url: str) -> None:
    """
    Initialise la session SQLAlchemy sync.

    @param database_url URL Postgres / SQLite.
    """
    db_module.SessionLocal = None
    asyncio.run(db_module.init_database(database_url))


def create_qdrant_collection(qdrant_url: str, collection: str = "intents") -> None:
    """
    Cree la collection Qdrant si elle n'existe pas encore.

    @param qdrant_url Base URL HTTP (ex. http://127.0.0.1:6333).
    @param collection Nom de collection.
    """
    base = qdrant_url.rstrip("/")
    info_url = f"{base}/collections/{collection}"
    with httpx.Client(timeout=30.0) as client:
        existing = client.get(info_url)
        if existing.status_code == 200:
            print(f"Collection deja presente: {collection}")
            return
        body = {
            "vectors": {"size": EMBED_DIM, "distance": "Cosine"},
            "optimizers_config": {"default_segment_number": 1},
        }
        created = client.put(info_url, json=body)
        if created.status_code not in (200, 201):
            raise RuntimeError(
                f"create_collection HTTP {created.status_code}: {created.text}"
            )
        print(f"Collection creee: {collection}")


def upsert_points(
    qdrant_url: str,
    collection: str,
    points: List[Dict[str, Any]],
) -> None:
    """
    Upsert un batch de points Qdrant.

    @param qdrant_url Base URL HTTP.
    @param collection Nom de collection.
    @param points Liste de points {id, vector, payload}.
    """
    url = (
        qdrant_url.rstrip("/")
        + f"/collections/{collection}/points?wait=true"
    )
    with httpx.Client(timeout=120.0) as client:
        response = client.put(url, json={"points": points})
        response.raise_for_status()


def fetch_embeddings(session) -> Any:
    """
    Iterateur sur les embeddings intents.

    @param session Session SQLAlchemy.
    @yields Tuples (id, intent_tag, ref_type, ref_id, vector).
    """
    sql = text(
        """
        SELECT e.id, i.tag AS intent_tag, e.ref_type, e.ref_id, e.embedding_json
        FROM intent_embeddings e
        JOIN intents i ON i.id = e.intent_id
        WHERE e.embedding_json IS NOT NULL
        ORDER BY e.id
        """
    )
    for row in session.execute(sql):
        yield row


def main() -> int:
    """
    Point d'entree CLI.

    @returns Code sortie (0 ok, 2 args manquants).
    """
    parser = argparse.ArgumentParser(description="Migrer intents -> Qdrant")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
    )
    parser.add_argument("--collection", default="intents")
    parser.add_argument("--batch", type=int, default=256)
    args = parser.parse_args()

    if not args.database_url:
        print("DATABASE_URL manquant", file=sys.stderr)
        return 2

    print("Initialisation DB...")
    ensure_db(args.database_url)
    print("Qdrant:", args.qdrant_url)
    create_qdrant_collection(args.qdrant_url, collection=args.collection)

    session = db_module.SessionLocal()
    try:
        batch: List[Dict[str, Any]] = []
        count = 0
        skipped = 0
        for row in fetch_embeddings(session):
            eid, tag, ref_type, ref_id, vec = row
            if not isinstance(vec, list) or len(vec) != EMBED_DIM:
                skipped += 1
                continue
            batch.append(
                {
                    "id": int(eid),
                    "vector": [float(x) for x in vec],
                    "payload": {
                        "intent_tag": str(tag),
                        "ref_type": str(ref_type),
                        "ref_id": int(ref_id),
                    },
                }
            )
            if len(batch) >= args.batch:
                upsert_points(args.qdrant_url, args.collection, batch)
                count += len(batch)
                print(f"Upserted {count} points")
                batch = []
        if batch:
            upsert_points(args.qdrant_url, args.collection, batch)
            count += len(batch)
            print(f"Upserted {count} points (final)")
        print(f"Migration terminee. points={count} skipped={skipped}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
