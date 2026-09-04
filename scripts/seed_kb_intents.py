"""
Seed one-shot des intents KB depuis data/intents/kb_seed/conversation_v1.json.

Usage:
  python scripts/seed_kb_intents.py
  python scripts/seed_kb_intents.py --replace
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.config import Config
from backend.database import database as db_module
from backend.services import intent_repository as intent_repo


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed intents KB Postgres")
    parser.add_argument("--replace", action="store_true", help="Recree les tags existants")
    args = parser.parse_args()

    config = Config()
    await db_module.init_database(config.database_url)
    db = db_module.SessionLocal()
    try:
        path = intent_repo.default_seed_path(Path(config.base_path or ROOT))
        catalog = intent_repo.load_seed_catalog(path)
        n = intent_repo.seed_intents_from_catalog(db, catalog, replace=args.replace)
        print(f"Seed OK: {n} intents ({path})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
