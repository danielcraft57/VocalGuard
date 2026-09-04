"""Extension pgvector + colonne embedding vectorielle pour intents.

Revision ID: 004_pgvector_intent_embeddings
Revises: 003_intents_normalized
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "004_pgvector_intent_embeddings"
down_revision: Union[str, Sequence[str], None] = "003_intents_normalized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBED_DIM = 384


def upgrade() -> None:
    """Active pgvector et index HNSW cosine sur intent_embeddings.embedding."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Colonne vector synchro depuis embedding_json via trigger applicatif / seed.
    op.execute(
        f"ALTER TABLE intent_embeddings "
        f"ADD COLUMN IF NOT EXISTS embedding vector({EMBED_DIM})"
    )
    # Remplit depuis JSON si deja seed avant migration.
    op.execute(
        """
        UPDATE intent_embeddings
        SET embedding = embedding_json::text::vector
        WHERE embedding IS NULL
          AND embedding_json IS NOT NULL
          AND jsonb_typeof(embedding_json) = 'array'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_intent_embeddings_hnsw_cosine
        ON intent_embeddings
        USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    """Retire index et colonne vector (garde embedding_json)."""
    op.execute("DROP INDEX IF EXISTS ix_intent_embeddings_hnsw_cosine")
    op.execute("ALTER TABLE intent_embeddings DROP COLUMN IF EXISTS embedding")
