"""Schema initial PostgreSQL normalise (VocalGuard).

Revision ID: 001_initial_pg
Revises:
Create Date: 2026-09-03

Schema neuf : pas d'import SQLite. JSON metier interdit ;
seul transcription_cues (JSONB) pour le karaoke SRT.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_pg"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree le schema cible via metadata SQLAlchemy."""
    from backend.database.models import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Supprime toutes les tables du schema VocalGuard."""
    from backend.database.models import Base

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
