"""
Match numeros entrants sur cache SQLite.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from desktop.prospector.campaign_store import CampaignStore
from desktop.prospector.db.models import PlEntreprise


def match_incoming_caller(session: Session, caller_id: Optional[str]) -> Optional[PlEntreprise]:
    """
    Recherche entreprise locale par CID.

    @param session Session SQLAlchemy.
    @param caller_id Numero entrant brut.
    @returns Entreprise ou None.
    """
    return CampaignStore(session).find_entreprise_by_phone(caller_id)
