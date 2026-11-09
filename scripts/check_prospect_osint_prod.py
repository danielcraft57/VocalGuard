#!/usr/bin/env python3
"""Smoke stats prospect OSINT (prod / local)."""
from backend.database.database import SessionLocal
from backend.database.models import ProspectPhone, ProspectPhoneImportBatch
from sqlalchemy import func

db = SessionLocal()
print("osint:", db.query(ProspectPhone.osint_status, func.count()).group_by(ProspectPhone.osint_status).all())
for b in db.query(ProspectPhoneImportBatch).order_by(ProspectPhoneImportBatch.id.desc()).limit(3):
    print("batch", b.id, b.phase, b.enrich_total, b.enrich_done, b.enrich_queued, b.enrich_failed)
print("queued_rows", db.query(ProspectPhone).filter(ProspectPhone.osint_status == "queued").count())
db.close()
