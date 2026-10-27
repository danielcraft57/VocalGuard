"""Enrichissement OSINT / ProspectLab + colonnes XLSX normalisees.

Revision ID: 009_prospect_phones_enrichment
Revises: 008_prospect_phones_normalized
Create Date: 2026-10-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_prospect_phones_enrichment"
down_revision: Union[str, Sequence[str], None] = "008_prospect_phones_normalized"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute tables google types et colonnes enrichissement."""
    op.create_table(
        "prospect_phone_google_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_prospect_phone_google_types_code", "prospect_phone_google_types", ["code"])
    op.create_index("ix_prospect_phone_google_types_label", "prospect_phone_google_types", ["label"])

    op.create_table(
        "prospect_phone_google_type_links",
        sa.Column("prospect_phone_id", sa.Integer(), nullable=False),
        sa.Column("google_type_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["google_type_id"], ["prospect_phone_google_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prospect_phone_id"], ["prospect_phones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("prospect_phone_id", "google_type_id"),
    )

    op.add_column("prospect_phone_import_batches", sa.Column("phase", sa.String(length=32), server_default="pending"))
    op.add_column("prospect_phone_import_batches", sa.Column("enrich_total", sa.Integer(), server_default="0"))
    op.add_column("prospect_phone_import_batches", sa.Column("enrich_done", sa.Integer(), server_default="0"))
    op.add_column("prospect_phone_import_batches", sa.Column("enrich_failed", sa.Integer(), server_default="0"))
    op.add_column("prospect_phone_import_batches", sa.Column("enrich_queued", sa.Integer(), server_default="0"))
    op.add_column("prospect_phone_import_batches", sa.Column("last_error", sa.String(length=500), nullable=True))

    for col, typ in [
        ("website", sa.String(500)),
        ("category_translate_raw", sa.String(500)),
        ("phone_profile_id", sa.Integer()),
        ("osint_status", sa.String(32)),
        ("prospectlab_status", sa.String(32)),
        ("prospectlab_entreprise_id", sa.Integer()),
        ("prospectlab_name", sa.String(255)),
        ("osint_company_name", sa.String(255)),
        ("osint_reputation", sa.String(32)),
        ("osint_operator", sa.String(128)),
        ("osint_region", sa.String(128)),
        ("name_match_status", sa.String(32)),
        ("enriched_at", sa.DateTime()),
    ]:
        op.add_column("prospect_phones", sa.Column(col, typ, nullable=True))

    op.create_foreign_key(
        "fk_prospect_phones_phone_profile_id",
        "prospect_phones",
        "phone_number_profiles",
        ["phone_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_prospect_phones_osint_status", "prospect_phones", ["osint_status"])
    op.create_index("ix_prospect_phones_prospectlab_status", "prospect_phones", ["prospectlab_status"])
    op.create_index("ix_prospect_phones_phone_profile_id", "prospect_phones", ["phone_profile_id"])


def downgrade() -> None:
    """Retire enrichissement prospect_phones."""
    op.drop_index("ix_prospect_phones_phone_profile_id", table_name="prospect_phones")
    op.drop_index("ix_prospect_phones_prospectlab_status", table_name="prospect_phones")
    op.drop_index("ix_prospect_phones_osint_status", table_name="prospect_phones")
    op.drop_constraint("fk_prospect_phones_phone_profile_id", "prospect_phones", type_="foreignkey")
    for col in (
        "enriched_at",
        "name_match_status",
        "osint_region",
        "osint_operator",
        "osint_reputation",
        "osint_company_name",
        "prospectlab_name",
        "prospectlab_entreprise_id",
        "prospectlab_status",
        "osint_status",
        "phone_profile_id",
        "category_translate_raw",
        "website",
    ):
        op.drop_column("prospect_phones", col)
    for col in ("last_error", "enrich_queued", "enrich_failed", "enrich_done", "enrich_total", "phase"):
        op.drop_column("prospect_phone_import_batches", col)
    op.drop_table("prospect_phone_google_type_links")
    op.drop_table("prospect_phone_google_types")
