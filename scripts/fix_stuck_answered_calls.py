#!/usr/bin/env python3
"""Marque completed les appels restes en answered (hangup bloque avant complete_call)."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import backend.database.database as db_module
from backend.database.models import Call


async def _init_db() -> None:
    url = os.environ.get("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'vocalguard.db'}")
    await db_module.init_database(url)


def main() -> None:
    asyncio.run(_init_db())
    db = db_module.SessionLocal()
    try:
        rows = db.query(Call).filter(Call.status == "answered").all()
        for call in rows:
            call.status = "completed"
            if not call.end_time:
                call.end_time = datetime.utcnow()
            if not call.duration:
                call.duration = 1
            print(f"fix call #{call.id} answered -> completed")
        db.commit()
        print(f"OK {len(rows)} appel(s) corrige(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
