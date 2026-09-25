"""Ajoute intents.profile + index (inbound | outbound_commercial).

Revision ID: 006_intent_profile
Revises: 005_kb_chat_sessions
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_intent_profile"
down_revision: Union[str, Sequence[str], None] = "005_kb_chat_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute la colonne profile (defaut inbound) et un index composite."""
    op.add_column(
        "intents",
        sa.Column(
            "profile",
            sa.String(length=40),
            nullable=False,
            server_default="inbound",
        ),
    )
    op.create_index(
        "ix_intents_profile_enabled_priority",
        "intents",
        ["profile", "enabled", "priority"],
        unique=False,
    )


def downgrade() -> None:
    """Retire profile et l'index."""
    op.drop_index("ix_intents_profile_enabled_priority", table_name="intents")
    op.drop_column("intents", "profile")
