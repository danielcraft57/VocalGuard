"""Sessions tchatche KB en Postgres.

Revision ID: 005_kb_chat_sessions
Revises: 004_pgvector_intent_embeddings
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_kb_chat_sessions"
down_revision: Union[str, Sequence[str], None] = "004_pgvector_intent_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree la table kb_chat_sessions."""
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "kb_chat_sessions",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Conversation"),
        sa.Column("messages", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recent_replies", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recent_tags", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("recent_user_texts", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_kb_chat_sessions_updated_at", "kb_chat_sessions", ["updated_at"])


def downgrade() -> None:
    """Supprime kb_chat_sessions."""
    op.drop_index("ix_kb_chat_sessions_updated_at", table_name="kb_chat_sessions")
    op.drop_table("kb_chat_sessions")
