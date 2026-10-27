"""Tables prospect_phones normalisees (import ProspectLab / verification tel).

Revision ID: 008_prospect_phones_normalized
Revises: 007_osint_reputation_normalized
Create Date: 2026-10-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_prospect_phones_normalized"
down_revision: Union[str, Sequence[str], None] = "007_osint_reputation_normalized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cree les tables d'import et prospects telephoniques."""
    op.create_table(
        "prospect_phone_import_batches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("source_city", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="excel"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_with_website", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_invalid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prospect_phone_import_batches_source_city",
        "prospect_phone_import_batches",
        ["source_city"],
        unique=False,
    )

    op.create_table(
        "prospect_phone_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_prospect_phone_categories_name", "prospect_phone_categories", ["name"], unique=False)
    op.create_index("ix_prospect_phone_categories_slug", "prospect_phone_categories", ["slug"], unique=False)

    op.create_table(
        "prospect_phones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=64), nullable=True),
        sa.Column("phone_digits", sa.String(length=64), nullable=True),
        sa.Column("source_city", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("postal_code", sa.String(length=16), nullable=True),
        sa.Column("address_1", sa.String(length=500), nullable=True),
        sa.Column("address_2", sa.String(length=500), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("reviews_count", sa.Integer(), nullable=True),
        sa.Column("google_categories_raw", sa.String(length=500), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_call_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["import_batch_id"], ["prospect_phone_import_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_call_id"], ["calls.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_digits", name="uq_prospect_phones_phone_digits"),
    )
    op.create_index("ix_prospect_phones_created_at", "prospect_phones", ["created_at"], unique=False)
    op.create_index("ix_prospect_phones_verification_status", "prospect_phones", ["verification_status"], unique=False)
    op.create_index("ix_prospect_phones_import_batch_id", "prospect_phones", ["import_batch_id"], unique=False)
    op.create_index("ix_prospect_phones_name", "prospect_phones", ["name"], unique=False)
    op.create_index("ix_prospect_phones_phone_digits", "prospect_phones", ["phone_digits"], unique=False)
    op.create_index("ix_prospect_phones_source_city", "prospect_phones", ["source_city"], unique=False)
    op.create_index("ix_prospect_phones_city", "prospect_phones", ["city"], unique=False)
    op.create_index("ix_prospect_phones_postal_code", "prospect_phones", ["postal_code"], unique=False)
    op.create_index("ix_prospect_phones_last_call_id", "prospect_phones", ["last_call_id"], unique=False)

    op.create_table(
        "prospect_phone_category_links",
        sa.Column("prospect_phone_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["prospect_phone_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prospect_phone_id"], ["prospect_phones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prospect_phone_id", "category_id"),
    )


def downgrade() -> None:
    """Supprime les tables prospect_phones."""
    op.drop_table("prospect_phone_category_links")
    op.drop_table("prospect_phones")
    op.drop_table("prospect_phone_categories")
    op.drop_index("ix_prospect_phone_import_batches_source_city", table_name="prospect_phone_import_batches")
    op.drop_table("prospect_phone_import_batches")
