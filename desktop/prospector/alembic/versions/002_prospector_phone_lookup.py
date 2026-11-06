"""002 index lookup telephone entrant.

Revision ID: 002_prospector_phone_lookup
Revises: 001_prospector_initial
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002_prospector_phone_lookup"
down_revision: Union[str, Sequence[str], None] = "001_prospector_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Index supplementaire sur pl_phone.phone_digits (deja indexe en 001, noop explicite)."""
    try:
        op.create_index("ix_pl_phone_digits_lookup", "pl_phone", ["phone_digits"], unique=False)
    except Exception:
        pass


def downgrade() -> None:
    """Retire l'index lookup."""
    try:
        op.drop_index("ix_pl_phone_digits_lookup", table_name="pl_phone")
    except Exception:
        pass
