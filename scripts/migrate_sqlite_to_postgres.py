#!/usr/bin/env python3
"""
Migrate data from a SQLite VocalGuard database into PostgreSQL.

Usage:
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite /opt/vocalguard/vocalguard_seed.db \
    --postgres "postgresql+psycopg2://user:pass@127.0.0.1:5432/vocalguard" \
    --truncate
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Dict, List, Sequence, Tuple

import psycopg2
from psycopg2.extras import execute_values


DEFAULT_TABLE_ORDER: List[str] = [
    "appointment_settings",
    "appointment_non_working_days",
    "entreprise_categories",
    "entreprises",
    "entreprise_emails",
    "entreprise_email_links",
    "entreprise_category_links",
    "clients",
    "calls",
    "voicemails",
    "agenda",
    "quotes",
    "api_public_tokens",
    "block_rules",
    "callers",
    "phone_number_profiles",
    "french_phone_prefixes",
    "entreprise_import_batches",
    "entreprise_import_rows",
    "entreprise_phone_analyses",
]


def _normalize_postgres_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg2://", "postgresql://", 1)


def _sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return [row[0] for row in cur.fetchall()]


def _postgres_tables(conn) -> List[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        return [row[0] for row in cur.fetchall()]


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _postgres_columns(conn, table: str) -> List[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def _postgres_column_types(conn, table: str) -> Dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def _rows_from_sqlite(conn: sqlite3.Connection, table: str, cols: Sequence[str]) -> List[Tuple]:
    cur = conn.cursor()
    col_sql = ", ".join(cols)
    cur.execute(f"SELECT {col_sql} FROM {table}")
    return cur.fetchall()


def _truncate_tables(conn, tables: Sequence[str]) -> None:
    if not tables:
        return
    sql = "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _insert_rows(conn, table: str, cols: Sequence[str], rows: Sequence[Tuple]) -> None:
    if not rows:
        return
    col_sql = ", ".join(f'"{c}"' for c in cols)
    sql = f'INSERT INTO "{table}" ({col_sql}) VALUES %s'
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=1000)


def _coerce_rows_for_pg(cols: Sequence[str], rows: Sequence[Tuple], pg_types: Dict[str, str]) -> List[Tuple]:
    coerced: List[Tuple] = []
    for row in rows:
        out = []
        for idx, value in enumerate(row):
            col = cols[idx]
            typ = pg_types.get(col, "")
            if value is None:
                out.append(None)
                continue
            if typ == "boolean":
                if isinstance(value, bool):
                    out.append(value)
                elif isinstance(value, (int, float)):
                    out.append(bool(value))
                elif isinstance(value, str):
                    out.append(value.strip().lower() in ("1", "true", "t", "yes", "on"))
                else:
                    out.append(bool(value))
            else:
                out.append(value)
        coerced.append(tuple(out))
    return coerced


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True, help="Path to source SQLite DB")
    parser.add_argument("--postgres", required=True, help="PostgreSQL SQLAlchemy URL or DSN")
    parser.add_argument("--truncate", action="store_true", help="Truncate target tables before import")
    args = parser.parse_args()

    sqlite_conn = sqlite3.connect(args.sqlite)
    pg_conn = psycopg2.connect(_normalize_postgres_dsn(args.postgres))
    pg_conn.autocommit = False

    sqlite_tables = set(_sqlite_tables(sqlite_conn))
    pg_tables = set(_postgres_tables(pg_conn))
    common_tables = sqlite_tables.intersection(pg_tables)

    ordered = [t for t in DEFAULT_TABLE_ORDER if t in common_tables]
    ordered += sorted(t for t in common_tables if t not in ordered)

    if args.truncate:
        _truncate_tables(pg_conn, ordered)

    imported: Dict[str, int] = {}
    for table in ordered:
        s_cols = _sqlite_columns(sqlite_conn, table)
        p_cols = _postgres_columns(pg_conn, table)
        p_types = _postgres_column_types(pg_conn, table)
        cols = [c for c in s_cols if c in p_cols]
        if not cols:
            imported[table] = 0
            continue

        rows = _rows_from_sqlite(sqlite_conn, table, cols)
        if not rows:
            imported[table] = 0
            continue

        rows = _coerce_rows_for_pg(cols, rows, p_types)
        _insert_rows(pg_conn, table, cols, rows)
        imported[table] = len(rows)

    pg_conn.commit()
    sqlite_conn.close()
    pg_conn.close()

    print("Migration done.")
    for table in ordered:
        print(f"{table}: {imported.get(table, 0)}")


if __name__ == "__main__":
    main()
