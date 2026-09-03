"""Indexes perf listes / stats / recherche.

Revision ID: 002_perf_indexes
Revises: 001_initial_pg
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "002_perf_indexes"
down_revision: Union[str, Sequence[str], None] = "001_initial_pg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ajoute indexes chauds + pg_trgm pour recherche entreprises."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Appels / messages / agenda
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_calls_status_call_time ON calls (status, call_time)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_voicemails_read_archived_created "
        "ON voicemails (is_read, is_archived, created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agenda_start_time ON agenda (start_time)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_agenda_created_at ON agenda (created_at)")

    # Callers filtering
    op.execute("CREATE INDEX IF NOT EXISTS ix_callers_is_blocked ON callers (is_blocked)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_callers_is_whitelisted ON callers (is_whitelisted)"
    )

    # Entreprises / clients / OSINT
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entreprises_created_at ON entreprises (created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_entreprises_country ON entreprises (country)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entreprises_name_trgm "
        "ON entreprises USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entreprises_city_trgm "
        "ON entreprises USING gin (city gin_trgm_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_clients_created_at ON clients (created_at)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phone_number_profiles_reputation "
        "ON phone_number_profiles (reputation)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phone_number_profiles_is_spam "
        "ON phone_number_profiles (is_spam)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phone_number_profiles_is_scam "
        "ON phone_number_profiles (is_scam)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_quotes_created_at ON quotes (created_at)")


def downgrade() -> None:
    """Supprime les indexes perf (garde l'extension pg_trgm)."""
    for name in (
        "ix_quotes_created_at",
        "ix_phone_number_profiles_is_scam",
        "ix_phone_number_profiles_is_spam",
        "ix_phone_number_profiles_reputation",
        "ix_clients_created_at",
        "ix_entreprises_city_trgm",
        "ix_entreprises_name_trgm",
        "ix_entreprises_country",
        "ix_entreprises_created_at",
        "ix_callers_is_whitelisted",
        "ix_callers_is_blocked",
        "ix_agenda_created_at",
        "ix_agenda_start_time",
        "ix_voicemails_read_archived_created",
        "ix_calls_status_call_time",
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")
