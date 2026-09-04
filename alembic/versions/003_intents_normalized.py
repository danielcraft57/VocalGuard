"""Tables intents normalisees (patterns, responses, embeddings JSON, call_leads).

Revision ID: 003_intents_normalized
Revises: 002_perf_indexes
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003_intents_normalized"
down_revision: Union[str, Sequence[str], None] = "002_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree intents / patterns / responses / embeddings / call_leads."""
    jsonb = postgresql.JSONB(astext_type=sa.Text())

    op.create_table(
        "intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False, server_default="seed"),
        sa.Column("niveau", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("wav_basename", sa.String(length=120), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_intents_tag", "intents", ["tag"], unique=True)
    op.create_index("ix_intents_enabled_priority", "intents", ["enabled", "priority"])

    op.create_table(
        "intent_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
    )
    op.create_index("ix_intent_patterns_intent_id", "intent_patterns", ["intent_id"])

    op.create_table(
        "intent_responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_index("ix_intent_responses_intent_id", "intent_responses", ["intent_id"])

    op.create_table(
        "intent_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent_id", sa.Integer(), sa.ForeignKey("intents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref_type", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("embedding_json", jsonb, nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False, server_default="384"),
        sa.UniqueConstraint("ref_type", "ref_id", name="uq_intent_embeddings_ref"),
    )
    op.create_index("ix_intent_embeddings_intent_id", "intent_embeddings", ["intent_id"])

    op.create_table(
        "call_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_number", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("callback_phone", sa.String(length=40), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("intent_tag", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_call_leads_call_id", "call_leads", ["call_id"])
    op.create_index("ix_call_leads_phone_number", "call_leads", ["phone_number"])


def downgrade() -> None:
    """Supprime les tables intents."""
    op.drop_table("call_leads")
    op.drop_table("intent_embeddings")
    op.drop_table("intent_responses")
    op.drop_table("intent_patterns")
    op.drop_index("ix_intents_enabled_priority", table_name="intents")
    op.drop_index("ix_intents_tag", table_name="intents")
    op.drop_table("intents")
