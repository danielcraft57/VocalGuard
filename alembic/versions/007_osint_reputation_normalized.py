"""Ajoute colonnes reputation OSINT + table sources normalisee (sans JSON).

Revision ID: 007_osint_reputation_normalized
Revises: 006_intent_profile
Create Date: 2026-09-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_osint_reputation_normalized"
down_revision: Union[str, Sequence[str], None] = "006_intent_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Etend phone_number_profiles et cree phone_osint_sources."""
    op.add_column(
        "phone_number_profiles",
        sa.Column("is_robocall", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("spam_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("spam_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("company_siren", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("company_siret", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("company_activity", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "phone_number_profiles",
        sa.Column("company_address", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_phone_number_profiles_is_robocall",
        "phone_number_profiles",
        ["is_robocall"],
        unique=False,
    )
    op.create_index(
        "ix_phone_number_profiles_spam_type",
        "phone_number_profiles",
        ["spam_type"],
        unique=False,
    )

    op.create_table(
        "phone_osint_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("source_code", sa.String(length=64), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["phone_number_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "source_code",
            name="uq_phone_osint_sources_profile_code",
        ),
    )
    op.create_index(
        "ix_phone_osint_sources_profile_id",
        "phone_osint_sources",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_phone_osint_sources_source_code",
        "phone_osint_sources",
        ["source_code"],
        unique=False,
    )

    # Drop legacy raw_data JSON si encore present (anciennes bases)
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("phone_number_profiles")}
    if "raw_data" in cols:
        op.drop_column("phone_number_profiles", "raw_data")


def downgrade() -> None:
    """Retire table sources et colonnes reputation."""
    op.drop_index("ix_phone_osint_sources_source_code", table_name="phone_osint_sources")
    op.drop_index("ix_phone_osint_sources_profile_id", table_name="phone_osint_sources")
    op.drop_table("phone_osint_sources")
    op.drop_index("ix_phone_number_profiles_spam_type", table_name="phone_number_profiles")
    op.drop_index("ix_phone_number_profiles_is_robocall", table_name="phone_number_profiles")
    op.drop_column("phone_number_profiles", "company_address")
    op.drop_column("phone_number_profiles", "company_activity")
    op.drop_column("phone_number_profiles", "company_siret")
    op.drop_column("phone_number_profiles", "company_siren")
    op.drop_column("phone_number_profiles", "spam_score")
    op.drop_column("phone_number_profiles", "spam_type")
    op.drop_column("phone_number_profiles", "is_robocall")
