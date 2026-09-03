#!/usr/bin/env python3
"""
Seed d'appels demo varies pour /calls (sans effacer les appels existants).

Usage sur node14 :
  cd /opt/vocalguard
  PYTHONPATH=/opt/vocalguard venv/bin/python scripts/seed_calls_demo.py
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("/opt/vocalguard/data/vocalguard.db")


def _now() -> datetime:
    return datetime.utcnow()


def main() -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"Base introuvable: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Nettoie seulement un precedent seed demo (marque metadata.seed=demo)
    old_ids = [
        row[0]
        for row in cur.execute(
            "SELECT id FROM calls WHERE metadata LIKE '%\"seed\": \"demo\"%' OR metadata LIKE '%\"seed\":\"demo\"%'"
        ).fetchall()
    ]
    if old_ids:
        placeholders = ",".join("?" * len(old_ids))
        cur.execute(f"DELETE FROM voicemails WHERE call_id IN ({placeholders})", old_ids)
        cur.execute(f"DELETE FROM calls WHERE id IN ({placeholders})", old_ids)
        print(f"Ancien seed demo supprime ({len(old_ids)} appels)")

    base = _now()
    demos = [
        {
            "phone": "0611223344",
            "name": "Jean Dupont",
            "status": "completed",
            "duration": 42,
            "hours_ago": 1,
            "direction": "in",
            "transcription": (
                "Bonjour, c'est Jean Dupont. Je vous rappelle pour le devis peinture "
                "de la cuisine. Vous pouvez me joindre cet apres-midi."
            ),
            "profile": "permitted",
        },
        {
            "phone": "0788990011",
            "name": "Sophie Martin",
            "status": "completed",
            "duration": 18,
            "hours_ago": 2,
            "direction": "in",
            "transcription": "Salut ! On confirme demain a 14h ? Bisous.",
            "profile": "permitted",
        },
        {
            "phone": "0387752832",
            "name": "Chia Bada",
            "status": "completed",
            "duration": 28,
            "hours_ago": 3,
            "direction": "in",
            "transcription": (
                "Bonjour M. Daniel, ici l'entreprise Chia Bada. "
                "Rappelez-moi au 03 87 75 28 32. Merci."
            ),
            "profile": "screened",
        },
        {
            "phone": "0622334455",
            "name": "Sortant",
            "status": "completed",
            "duration": 65,
            "hours_ago": 4,
            "direction": "out",
            "transcription": "Allô Pierre ? Oui c'est moi, je te rappelle pour VocalGuard.",
            "profile": "permitted",
        },
        {
            "phone": "0899123456",
            "name": "Pub aggressive",
            "status": "blocked",
            "duration": 0,
            "hours_ago": 5,
            "direction": "in",
            "transcription": None,
            "profile": "blocked",
        },
        {
            "phone": "0677001122",
            "name": None,
            "status": "missed",
            "duration": 0,
            "hours_ago": 6,
            "direction": "in",
            "transcription": None,
            "profile": "screened",
        },
        {
            "phone": "0142434445",
            "name": "Cabinet Dr Laurent",
            "status": "completed",
            "duration": 22,
            "hours_ago": 8,
            "direction": "in",
            "transcription": (
                "Bonjour, cabinet medical du Dr Laurent. Votre rendez-vous est "
                "confirme vendredi a 10h30."
            ),
            "profile": "permitted",
        },
        {
            "phone": "0612345678",
            "name": "Sortant",
            "status": "missed",
            "duration": 0,
            "hours_ago": 10,
            "direction": "out",
            "transcription": None,
            "profile": "screened",
        },
        {
            "phone": "0699887766",
            "name": "Marie Leroy",
            "status": "answered",
            "duration": 95,
            "hours_ago": 12,
            "direction": "in",
            "transcription": (
                "Coucou c'est Marie, j'ai laisse un message tout a l'heure. "
                "Rappelle-moi quand tu es dispo, pas urgent."
            ),
            "profile": "permitted",
        },
        {
            "phone": "0800123456",
            "name": "Demarchage auto",
            "status": "blocked",
            "duration": 0,
            "hours_ago": 14,
            "direction": "in",
            "transcription": None,
            "profile": "blocked",
        },
        {
            "phone": "0755667788",
            "name": "Lucas Bernard",
            "status": "completed",
            "duration": 11,
            "hours_ago": 20,
            "direction": "in",
            "transcription": "Hey, c'est Lucas. Rien de special, juste un petit coucou.",
            "profile": "screened",
        },
        {
            "phone": "0323456789",
            "name": "Sortant",
            "status": "completed",
            "duration": 140,
            "hours_ago": 26,
            "direction": "out",
            "transcription": (
                "Oui allô, je vous appelle pour confirmer la livraison de demain matin."
            ),
            "profile": "permitted",
        },
    ]

    inserted = 0
    for item in demos:
        call_time = base - timedelta(hours=item["hours_ago"])
        answer = call_time + timedelta(seconds=3) if item["status"] in ("completed", "answered") else None
        end = (
            call_time + timedelta(seconds=3 + int(item["duration"] or 0))
            if item["status"] in ("completed", "answered")
            else None
        )
        meta = {
            "seed": "demo",
            "direction": item["direction"],
            "incoming_profile": item["profile"],
        }
        audio = None
        if item["direction"] == "out" and item["status"] == "completed":
            audio = f"recordings/call_out_seed_{inserted + 1}.wav"
        elif item["status"] in ("completed", "answered"):
            audio = f"recordings/call_in_seed_{inserted + 1}.wav"

        cur.execute(
            """
            INSERT INTO calls (
              caller_id, phone_number, caller_name, call_time, answer_time, end_time,
              status, duration, transcription, audio_file, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                item["phone"],
                item["name"],
                call_time.isoformat(sep=" "),
                answer.isoformat(sep=" ") if answer else None,
                end.isoformat(sep=" ") if end else None,
                item["status"],
                item["duration"] or None,
                item["transcription"],
                audio,
                json.dumps(meta, ensure_ascii=False),
                call_time.isoformat(sep=" "),
            ),
        )
        call_id = cur.lastrowid
        inserted += 1

        if item["transcription"] and item["status"] in ("completed", "answered"):
            cur.execute(
                """
                INSERT INTO voicemails (
                  call_id, caller_id, phone_number, caller_name, audio_file,
                  transcription, duration, is_read, is_archived, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    None,
                    item["phone"],
                    item["name"],
                    f"messages/vm_seed_{call_id}.wav",
                    item["transcription"],
                    item["duration"] or 10,
                    1 if inserted % 3 == 0 else 0,
                    0,
                    call_time.isoformat(sep=" "),
                ),
            )

    conn.commit()
    total = cur.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    conn.close()
    print(f"Seed OK: {inserted} appels demo ajoutes (total calls={total})")


if __name__ == "__main__":
    # Permet aussi un chemin local via VOCALGUARD_DB
    env_db = os.environ.get("VOCALGUARD_DB", "").strip()
    if env_db:
        DB_PATH = Path(env_db)  # noqa: N806
    main()
