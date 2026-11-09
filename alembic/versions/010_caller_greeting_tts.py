"""Accueil TTS personnalise par appelant (liste blanche).

Revision ID: 010_caller_greeting_tts
Revises: 009_prospect_phones_enrichment
Create Date: 2026-11-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_caller_greeting_tts"
down_revision: Union[str, Sequence[str], None] = "009_prospect_phones_enrichment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute greeting_tts_text sur callers."""
    op.add_column("callers", sa.Column("greeting_tts_text", sa.Text(), nullable=True))


def downgrade() -> None:
    """Retire greeting_tts_text."""
    op.drop_column("callers", "greeting_tts_text")
