#!/usr/bin/env python3
"""
Migre les embeddings d'intents depuis Postgres vers Qdrant.

Usage:
  export DATABASE_URL=postgresql+psycopg2://user:pass@node14.lan:5432/vocalguard
  export QDRANT_URL=http://127.0.0.1:6333
  python scripts/migrate_intents_to_qdrant.py --profile inbound
  python scripts/migrate_intents_to_qdrant.py --profile outbound_commercial
  python scripts/migrate_intents_to_qdrant.py --rename-legacy

Collections :
- intents_inbound (appels entrants)
- intents_outbound_commercial (appel commercial sortant)
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
from backend.voice.qdrant_intents import (
    COLLECTION_INBOUND,
    COLLECTION_OUTBOUND_COMMERCIAL,
    LEGACY_COLLECTION,
    PROFILE_INBOUND,
    PROFILE_OUTBOUND_COMMERCIAL,
    collection_for_profile,
    delete_collection,
)


def ensure_db(database_url: str) -> None:
    """
    Initialise la session SQLAlchemy sync.

    @param database_url URL Postgres / SQLite.
    """
    db_module.SessionLocal = None
    asyncio.run(db_module.init_database(database_url))


def create_qdrant_collection(qdrant_url: str, collection: str) -> None:
    """
    Cree la collection Qdrant si elle n'existe pas encore.

    @param qdrant_url Base URL HTTP.
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


def fetch_embeddings(session, profile: Optional[str] = None):
    """
    Iterateur sur les embeddings intents.

    @param session Session SQLAlchemy.
    @param profile Filtre profil optionnel.
    @yields Tuples (id, intent_tag, ref_type, ref_id, profile, vector).
    """
    if profile:
        sql = text(
            """
            SELECT e.id, i.tag AS intent_tag, e.ref_type, e.ref_id,
                   i.profile AS profile, e.embedding_json
            FROM intent_embeddings e
            JOIN intents i ON i.id = e.intent_id
            WHERE e.embedding_json IS NOT NULL
              AND i.profile = :profile
            ORDER BY e.id
            """
        )
        rows = session.execute(sql, {"profile": profile})
    else:
        sql = text(
            """
            SELECT e.id, i.tag AS intent_tag, e.ref_type, e.ref_id,
                   COALESCE(i.profile, 'inbound') AS profile, e.embedding_json
            FROM intent_embeddings e
            JOIN intents i ON i.id = e.intent_id
            WHERE e.embedding_json IS NOT NULL
            ORDER BY e.id
            """
        )
        rows = session.execute(sql)
    for row in rows:
        yield row


def migrate_profile(
    session,
    qdrant_url: str,
    profile: str,
    *,
    batch_size: int = 256,
) -> int:
    """
    Migre un profil vers sa collection Qdrant.

    @param session Session DB.
    @param qdrant_url URL Qdrant.
    @param profile Profil KB.
    @param batch_size Taille batch upsert.
    @returns Nombre de points upsertes.
    """
    collection = collection_for_profile(profile)
    create_qdrant_collection(qdrant_url, collection)
    batch: List[Dict[str, Any]] = []
    count = 0
    skipped = 0
    for row in fetch_embeddings(session, profile=profile):
        eid, tag, ref_type, ref_id, prof, vec = row
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
                    "profile": str(prof or profile),
                },
            }
        )
        if len(batch) >= batch_size:
            upsert_points(qdrant_url, collection, batch)
            count += len(batch)
            print(f"[{profile}] Upserted {count} points")
            batch = []
    if batch:
        upsert_points(qdrant_url, collection, batch)
        count += len(batch)
        print(f"[{profile}] Upserted {count} points (final)")
    print(f"[{profile} -> {collection}] done points={count} skipped={skipped}")
    return count


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
    parser.add_argument(
        "--profile",
        choices=[PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL, "all"],
        default="all",
        help="Profil a migrer (defaut: all)",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Override nom collection (sinon derive du profil)",
    )
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument(
        "--rename-legacy",
        action="store_true",
        help="Apres migrate inbound: supprimer l'ancienne collection 'intents'",
    )
    args = parser.parse_args()

    if not args.database_url:
        print("DATABASE_URL manquant", file=sys.stderr)
        return 2

    print("Initialisation DB...")
    ensure_db(args.database_url)
    print("Qdrant:", args.qdrant_url)

    session = db_module.SessionLocal()
    try:
        profiles = (
            [PROFILE_INBOUND, PROFILE_OUTBOUND_COMMERCIAL]
            if args.profile == "all"
            else [args.profile]
        )
        for prof in profiles:
            if args.collection and len(profiles) == 1:
                # Override manuel : migre dans la collection demandee
                create_qdrant_collection(args.qdrant_url, args.collection)
                batch: List[Dict[str, Any]] = []
                count = 0
                for row in fetch_embeddings(session, profile=prof):
                    eid, tag, ref_type, ref_id, profile_val, vec = row
                    if not isinstance(vec, list) or len(vec) != EMBED_DIM:
                        continue
                    batch.append(
                        {
                            "id": int(eid),
                            "vector": [float(x) for x in vec],
                            "payload": {
                                "intent_tag": str(tag),
                                "ref_type": str(ref_type),
                                "ref_id": int(ref_id),
                                "profile": str(profile_val or prof),
                            },
                        }
                    )
                    if len(batch) >= args.batch:
                        upsert_points(args.qdrant_url, args.collection, batch)
                        count += len(batch)
                        batch = []
                if batch:
                    upsert_points(args.qdrant_url, args.collection, batch)
                    count += len(batch)
                print(f"Override collection={args.collection} points={count}")
            else:
                migrate_profile(
                    session, args.qdrant_url, prof, batch_size=args.batch
                )

        if args.rename_legacy:
            print(f"Suppression collection legacy '{LEGACY_COLLECTION}'...")
            # S'assurer que inbound existe avant delete
            create_qdrant_collection(args.qdrant_url, COLLECTION_INBOUND)
            ok = delete_collection(
                qdrant_url=args.qdrant_url, collection=LEGACY_COLLECTION
            )
            print("Legacy supprimee" if ok else "Echec suppression legacy")
            print(
                f"Collections cibles: {COLLECTION_INBOUND}, "
                f"{COLLECTION_OUTBOUND_COMMERCIAL}"
            )
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
