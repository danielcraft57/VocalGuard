#!/usr/bin/env python3
"""
Regenere les caches accueil known / unknown / commercial sur le Pi (prod).

Usage :
  cd /opt/vocalguard
  source venv/bin/activate
  export PYTHONPATH=/opt/vocalguard VG_ENV=prod
  python scripts/regenerate_all_greetings_pi.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.call_manager import CallManager
from backend.core.config import Config
from backend.core.greeting_audiences import GREETING_AUDIENCE_KEYS
from backend.database import database as db_module


async def main() -> int:
    """
    Force la regeneration des WAV modem actifs pour chaque audience.

    @returns 0 si tout s'est bien passe.
    """
    config = Config()
    config.base_path = ROOT
    await db_module.init_database(config.database_url)
    db = db_module.SessionLocal()
    try:
        cm = CallManager(config, db)
        await cm.initialize()
        for audience in GREETING_AUDIENCE_KEYS:
            data = await cm.regenerate_greeting_cache(audience=audience)
            print(
                "ok",
                audience,
                data.get("provider"),
                data.get("voice"),
                data.get("track_wav"),
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))