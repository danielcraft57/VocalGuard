"""Schema initial Prospector SQLite.

Revision ID: 001_prospector_initial
Revises:
Create Date: 2026-11-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "001_prospector_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree toutes les tables Prospector."""
    from desktop.prospector.db.models import ProspectorBase

    bind = op.get_bind()
    ProspectorBase.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Supprime toutes les tables Prospector."""
    from desktop.prospector.db.models import ProspectorBase

    bind = op.get_bind()
    ProspectorBase.metadata.drop_all(bind=bind)
