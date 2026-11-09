"""
Gestion de la base de donnees (SQLAlchemy sync).

SQLite : create_all + migrations legeres (dev).
PostgreSQL : pool configure ; schema via Alembic (pas de create_all par defaut).
"""

import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from backend.database.models import Base


# Factory de sessions synchrones
SessionLocal = None


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    """
    Lit une variable d environnement entiere bornee.

    @param name Nom de la variable.
    @param default Valeur si absente ou invalide.
    @param minimum Borne basse incluse.
    @param maximum Borne haute incluse.
    @returns Entier dans [minimum, maximum].
    """
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


async def init_database(database_url: str) -> None:
    """
    Initialise la base de donnees.

    @param database_url URL de connexion (sqlite:///... ou postgresql+psycopg2://...).
    """
    global SessionLocal

    logger.info(f"Initialisation de la base de donnees: {database_url}")

    is_sqlite = database_url.startswith("sqlite")
    is_postgres = database_url.startswith("postgresql") or database_url.startswith("postgres")

    engine_kwargs = {"echo": False, "pool_pre_ping": True}
    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    elif is_postgres:
        pool_size = _env_int("VG_DB_POOL_SIZE", 5, 1, 50)
        max_overflow = _env_int("VG_DB_MAX_OVERFLOW", 10, 0, 50)
        engine_kwargs.update(
            {
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_recycle": 1800,
                "pool_timeout": 30,
            }
        )
        logger.info(
            "Pool PostgreSQL: pool_size={} max_overflow={}",
            pool_size,
            max_overflow,
        )

    engine = create_engine(database_url, **engine_kwargs)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[unused-argument]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    autocreate = os.getenv("VG_DB_AUTOCREATE", "").strip().lower() in ("1", "true", "yes")
    if is_sqlite or autocreate:
        Base.metadata.create_all(bind=engine)
        logger.info("create_all applique (sqlite ou VG_DB_AUTOCREATE)")
    elif is_postgres:
        logger.info("PostgreSQL: schema attendu via Alembic (pas de create_all)")

    if is_sqlite:
        _apply_lightweight_migrations(engine)
    elif is_postgres:
        _apply_postgres_call_foreign_keys(engine)

    logger.info("Base de donnees initialisee")


def _apply_postgres_call_foreign_keys(engine) -> None:
    """Aligne les FK appels (CASCADE / SET NULL) sur PostgreSQL existant."""
    if engine.dialect.name != "postgresql":
        return
    stmts = [
        "ALTER TABLE voicemails DROP CONSTRAINT IF EXISTS voicemails_call_id_fkey",
        "ALTER TABLE voicemails ADD CONSTRAINT voicemails_call_id_fkey "
        "FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE",
        "ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_caller_id_fkey",
        "ALTER TABLE calls ADD CONSTRAINT calls_caller_id_fkey "
        "FOREIGN KEY (caller_id) REFERENCES callers(id) ON DELETE SET NULL",
        "ALTER TABLE agenda DROP CONSTRAINT IF EXISTS agenda_source_call_id_fkey",
        "ALTER TABLE agenda ADD CONSTRAINT agenda_source_call_id_fkey "
        "FOREIGN KEY (source_call_id) REFERENCES calls(id) ON DELETE SET NULL",
    ]
    try:
        with engine.begin() as conn:
            for sql in stmts:
                conn.execute(text(sql))
        logger.info("Contraintes FK appels PostgreSQL mises a jour (CASCADE voicemails / SET NULL)")
    except Exception as exc:
        logger.warning("Migration FK appels PostgreSQL ignoree ou partielle: {}", exc)


def _apply_lightweight_migrations(engine) -> None:
    """
    Applique des migrations legeres compatibles SQLite dev.

    En PostgreSQL, utiliser Alembic (runtime saute cette etape).
    """
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "customers" in table_names and "clients" not in table_names:
            conn.execute(text("ALTER TABLE customers RENAME TO clients"))
            logger.info("Migration légère appliquée: table customers renommee en clients")
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())

        if "appointments" in table_names and "agenda" not in table_names:
            conn.execute(text("ALTER TABLE appointments RENAME TO agenda"))
            logger.info("Migration légère appliquée: table appointments renommee en agenda")
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())

        if "calls" in table_names:
            cols = {col["name"] for col in inspector.get_columns("calls")}
            if "customer_id" in cols and "client_id" not in cols:
                conn.execute(text("ALTER TABLE calls RENAME COLUMN customer_id TO client_id"))
                logger.info("Migration légère appliquée: calls.customer_id -> calls.client_id")
            for col_name, ddl in (
                ("incoming_profile", "ALTER TABLE calls ADD COLUMN incoming_profile VARCHAR(32)"),
                ("incoming_policy_source", "ALTER TABLE calls ADD COLUMN incoming_policy_source VARCHAR(128)"),
                ("incoming_rings", "ALTER TABLE calls ADD COLUMN incoming_rings INTEGER"),
                ("incoming_ignored", "ALTER TABLE calls ADD COLUMN incoming_ignored BOOLEAN NOT NULL DEFAULT 0"),
                ("no_message", "ALTER TABLE calls ADD COLUMN no_message BOOLEAN NOT NULL DEFAULT 0"),
                ("no_message_reason", "ALTER TABLE calls ADD COLUMN no_message_reason VARCHAR(80)"),
                ("ui_tag", "ALTER TABLE calls ADD COLUMN ui_tag VARCHAR(64)"),
                ("ivr_intent", "ALTER TABLE calls ADD COLUMN ivr_intent VARCHAR(100)"),
                ("transcription_cues", "ALTER TABLE calls ADD COLUMN transcription_cues JSON"),
            ):
                if col_name not in cols:
                    conn.execute(text(ddl))
                    logger.info("Migration légère appliquée: calls.{} ajoute", col_name)
                    cols.add(col_name)

        if "voicemails" in table_names:
            cols = {col["name"] for col in inspector.get_columns("voicemails")}
            if "customer_id" in cols and "client_id" not in cols:
                conn.execute(text("ALTER TABLE voicemails RENAME COLUMN customer_id TO client_id"))
                logger.info("Migration légère appliquée: voicemails.customer_id -> voicemails.client_id")
            if "transcription_cues" not in cols:
                conn.execute(text("ALTER TABLE voicemails ADD COLUMN transcription_cues JSON"))
                logger.info("Migration légère appliquée: voicemails.transcription_cues ajoute")

        if "agenda" in table_names:
            columns = {col["name"] for col in inspector.get_columns("agenda")}
            if "customer_id" in columns and "client_id" not in columns:
                conn.execute(text("ALTER TABLE agenda RENAME COLUMN customer_id TO client_id"))
                logger.info("Migration légère appliquée: agenda.customer_id -> agenda.client_id")
            if "source_call_id" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN source_call_id INTEGER"))
                logger.info("Migration légère appliquée: agenda.source_call_id ajouté")
            if "entreprise_id" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN entreprise_id INTEGER"))
                logger.info("Migration légère appliquée: agenda.entreprise_id ajouté")
            if "agenda_tag" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN agenda_tag VARCHAR(50)"))
                logger.info("Migration légère appliquée: agenda.agenda_tag ajouté")
            if "display_icon" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN display_icon VARCHAR(50)"))
                logger.info("Migration légère appliquée: agenda.display_icon ajouté")
            if "display_color" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN display_color VARCHAR(20)"))
                logger.info("Migration légère appliquée: agenda.display_color ajouté")
            if "is_all_day" not in columns:
                conn.execute(text("ALTER TABLE agenda ADD COLUMN is_all_day BOOLEAN NOT NULL DEFAULT 0"))
                logger.info("Migration légère appliquée: agenda.is_all_day ajouté")

        if "quotes" in table_names:
            cols = {col["name"] for col in inspector.get_columns("quotes")}
            if "customer_id" in cols and "client_id" not in cols:
                conn.execute(text("ALTER TABLE quotes RENAME COLUMN customer_id TO client_id"))
                logger.info("Migration légère appliquée: quotes.customer_id -> quotes.client_id")

        if "clients" in table_names:
            cols = {col["name"] for col in inspector.get_columns("clients")}
            if "entreprise_id" not in cols:
                conn.execute(text("ALTER TABLE clients ADD COLUMN entreprise_id INTEGER"))
                logger.info("Migration légère appliquée: clients.entreprise_id ajouté")

        if "api_public_tokens" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE api_public_tokens (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        app_url VARCHAR(500),
                        token VARCHAR(128) NOT NULL UNIQUE,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        can_read_agenda BOOLEAN NOT NULL DEFAULT 1,
                        can_write_agenda BOOLEAN NOT NULL DEFAULT 1,
                        can_write_entreprises BOOLEAN NOT NULL DEFAULT 1,
                        can_manage_tokens BOOLEAN NOT NULL DEFAULT 0,
                        can_read_customers BOOLEAN NOT NULL DEFAULT 0,
                        can_write_customers BOOLEAN NOT NULL DEFAULT 0,
                        can_read_quotes BOOLEAN NOT NULL DEFAULT 0,
                        can_write_quotes BOOLEAN NOT NULL DEFAULT 0,
                        can_read_calls BOOLEAN NOT NULL DEFAULT 0,
                        created_at DATETIME,
                        last_used_at DATETIME
                    )
                    """
                )
            )
            conn.execute(text("CREATE UNIQUE INDEX ix_api_public_tokens_token ON api_public_tokens (token)"))
            logger.info("Migration légère appliquée: table api_public_tokens créée")
        else:
            token_columns = {col["name"] for col in inspector.get_columns("api_public_tokens")}
            if "app_url" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN app_url VARCHAR(500)"))
            if "can_read_agenda" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_read_agenda BOOLEAN NOT NULL DEFAULT 1"))
            if "can_write_agenda" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_agenda BOOLEAN NOT NULL DEFAULT 1"))
            if "can_write_entreprises" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_entreprises BOOLEAN NOT NULL DEFAULT 1"))
            if "can_manage_tokens" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_manage_tokens BOOLEAN NOT NULL DEFAULT 0"))
            if "can_read_customers" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_read_customers BOOLEAN NOT NULL DEFAULT 0"))
            if "can_write_customers" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_customers BOOLEAN NOT NULL DEFAULT 0"))
            if "can_read_quotes" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_read_quotes BOOLEAN NOT NULL DEFAULT 0"))
            if "can_write_quotes" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_quotes BOOLEAN NOT NULL DEFAULT 0"))
            if "can_read_calls" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_read_calls BOOLEAN NOT NULL DEFAULT 0"))
            if "can_read_voicemails" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_read_voicemails BOOLEAN NOT NULL DEFAULT 0"))
            if "can_write_calls" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_calls BOOLEAN NOT NULL DEFAULT 0"))
            if "can_subscribe_realtime" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_subscribe_realtime BOOLEAN NOT NULL DEFAULT 0"))
            if "can_write_trusted" not in token_columns:
                conn.execute(text("ALTER TABLE api_public_tokens ADD COLUMN can_write_trusted BOOLEAN NOT NULL DEFAULT 0"))

        if "entreprise_emails" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE entreprise_emails (
                        id INTEGER PRIMARY KEY,
                        email VARCHAR(320) NOT NULL UNIQUE,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            conn.execute(text("CREATE UNIQUE INDEX ix_entreprise_emails_email ON entreprise_emails (email)"))
            logger.info("Migration légère appliquée: table entreprise_emails créée")

        if "entreprise_email_links" not in table_names:
            conn.execute(
                text(
                    """
                    CREATE TABLE entreprise_email_links (
                        entreprise_id INTEGER NOT NULL,
                        email_id INTEGER NOT NULL,
                        PRIMARY KEY (entreprise_id, email_id),
                        FOREIGN KEY(entreprise_id) REFERENCES entreprises(id) ON DELETE CASCADE,
                        FOREIGN KEY(email_id) REFERENCES entreprise_emails(id) ON DELETE CASCADE
                    )
                    """
                )
            )
            logger.info("Migration légère appliquée: table entreprise_email_links créée")

        _migrate_prospect_phones_sqlite(conn, inspector, table_names)

    _sqlite_add_missing_model_columns(engine)


def _sqlite_type_sql(col) -> str:
    """Type SQLite approximatif pour un ALTER TABLE ADD COLUMN."""
    from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text, Time

    t = col.type
    if isinstance(t, Boolean):
        return "BOOLEAN"
    if isinstance(t, Integer):
        return "INTEGER"
    if isinstance(t, Float):
        return "FLOAT"
    if isinstance(t, DateTime):
        return "DATETIME"
    if isinstance(t, Date):
        return "DATE"
    if isinstance(t, Time):
        return "TIME"
    if isinstance(t, Text):
        return "TEXT"
    if isinstance(t, String):
        return f"VARCHAR({t.length or 255})"
    return "TEXT"


def _sqlite_column_default_sql(col) -> str:
    """Default SQL si la valeur est un scalaire (pas un callable)."""
    default = getattr(col, "default", None)
    arg = getattr(default, "arg", None) if default is not None else None
    if arg is None or callable(arg):
        server = getattr(col, "server_default", None)
        server_arg = getattr(getattr(server, "arg", None), "text", None) if server is not None else None
        if isinstance(server_arg, str) and server_arg.strip():
            return f" DEFAULT {server_arg.strip()}"
        return ""
    if isinstance(arg, bool):
        return f" DEFAULT {1 if arg else 0}"
    if isinstance(arg, (int, float)):
        return f" DEFAULT {arg}"
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f" DEFAULT '{escaped}'"
    return ""


def _sqlite_add_missing_model_columns(engine) -> None:
    """
    Aligne SQLite sur les modeles SQLAlchemy.

    create_all cree les tables absentes mais n'ajoute pas les colonnes
    sur une table deja la (cas Alembic non joue en local).
    """
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    added = 0
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have or col.primary_key:
                    continue
                sql_type = _sqlite_type_sql(col)
                default_sql = _sqlite_column_default_sql(col)
                nullable = bool(col.nullable)
                if not nullable and not default_sql:
                    default_sql = " DEFAULT 0" if sql_type in ("INTEGER", "FLOAT", "BOOLEAN") else " DEFAULT ''"
                null_sql = "" if not nullable else ""
                if nullable:
                    null_sql = ""
                else:
                    null_sql = " NOT NULL"
                ddl = (
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" '
                    f"{sql_type}{null_sql}{default_sql}"
                )
                conn.execute(text(ddl))
                added += 1
                logger.info("SQLite: colonne ajoutee {}.{}", table.name, col.name)
    if added:
        logger.info("SQLite: {} colonne(s) manquante(s) ajoutee(s)", added)


def _migrate_prospect_phones_sqlite(conn, inspector, table_names: set) -> None:
    """Ajoute les colonnes d'enrichissement si la table existait deja (create_all ne les ajoute pas)."""
    if "prospect_phones" not in table_names:
        return
    cols = {col["name"] for col in inspector.get_columns("prospect_phones")}
    additions = (
        ("website", "ALTER TABLE prospect_phones ADD COLUMN website VARCHAR(500)"),
        ("category_translate_raw", "ALTER TABLE prospect_phones ADD COLUMN category_translate_raw VARCHAR(500)"),
        ("phone_profile_id", "ALTER TABLE prospect_phones ADD COLUMN phone_profile_id INTEGER"),
        ("osint_status", "ALTER TABLE prospect_phones ADD COLUMN osint_status VARCHAR(32) NOT NULL DEFAULT 'pending'"),
        ("prospectlab_status", "ALTER TABLE prospect_phones ADD COLUMN prospectlab_status VARCHAR(32) NOT NULL DEFAULT 'pending'"),
        ("prospectlab_entreprise_id", "ALTER TABLE prospect_phones ADD COLUMN prospectlab_entreprise_id INTEGER"),
        ("prospectlab_name", "ALTER TABLE prospect_phones ADD COLUMN prospectlab_name VARCHAR(255)"),
        ("osint_company_name", "ALTER TABLE prospect_phones ADD COLUMN osint_company_name VARCHAR(255)"),
        ("osint_reputation", "ALTER TABLE prospect_phones ADD COLUMN osint_reputation VARCHAR(32)"),
        ("osint_operator", "ALTER TABLE prospect_phones ADD COLUMN osint_operator VARCHAR(128)"),
        ("osint_region", "ALTER TABLE prospect_phones ADD COLUMN osint_region VARCHAR(128)"),
        ("name_match_status", "ALTER TABLE prospect_phones ADD COLUMN name_match_status VARCHAR(32)"),
        ("enriched_at", "ALTER TABLE prospect_phones ADD COLUMN enriched_at DATETIME"),
    )
    for name, ddl in additions:
        if name not in cols:
            conn.execute(text(ddl))
            logger.info("Migration sqlite: prospect_phones.{}", name)

    if "prospect_phone_import_batches" in table_names:
        batch_cols = {col["name"] for col in inspector.get_columns("prospect_phone_import_batches")}
        for name, ddl in (
            ("phase", "ALTER TABLE prospect_phone_import_batches ADD COLUMN phase VARCHAR(32) NOT NULL DEFAULT 'pending'"),
            ("enrich_total", "ALTER TABLE prospect_phone_import_batches ADD COLUMN enrich_total INTEGER NOT NULL DEFAULT 0"),
            ("enrich_done", "ALTER TABLE prospect_phone_import_batches ADD COLUMN enrich_done INTEGER NOT NULL DEFAULT 0"),
            ("enrich_failed", "ALTER TABLE prospect_phone_import_batches ADD COLUMN enrich_failed INTEGER NOT NULL DEFAULT 0"),
            ("enrich_queued", "ALTER TABLE prospect_phone_import_batches ADD COLUMN enrich_queued INTEGER NOT NULL DEFAULT 0"),
            ("last_error", "ALTER TABLE prospect_phone_import_batches ADD COLUMN last_error VARCHAR(500)"),
        ):
            if name not in batch_cols:
                conn.execute(text(ddl))
                logger.info("Migration sqlite: prospect_phone_import_batches.{}", name)


def get_db() -> Session:
    """
    Fournit une session de base de donnees synchrone.

    @raises RuntimeError si la base n'a pas encore ete initialisee.
    """
    if SessionLocal is None:
        raise RuntimeError("Base de donnees non initialisee")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
