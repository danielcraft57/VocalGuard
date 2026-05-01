"""
Gestion de la base de données (mode synchrone simple pour le développement).

On utilise un engine SQLAlchemy classique et une seule factory de sessions.
L'initialisation est déclenchée au démarrage de l'application FastAPI.
"""

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from backend.database.models import Base


# Factory de sessions synchrones
SessionLocal = None


async def init_database(database_url: str) -> None:
    """
    Initialise la base de données.
    
    Args:
        database_url: URL de connexion à la base de données.
    """
    global SessionLocal

    logger.info(f"Initialisation de la base de données: {database_url}")

    # Engine synchrone (compatible SQLite et PostgreSQL)
    engine_kwargs = {"echo": False, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        # SQLite: same-thread off pour usage API + workers locaux
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(database_url, **engine_kwargs)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[unused-argument]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Factory de sessions
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Création des tables
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations(engine)

    logger.info("Base de données initialisée")


def _apply_lightweight_migrations(engine) -> None:
    """
    Applique des migrations légères compatibles dev.

    Contexte: on utilise create_all sans Alembic automatique au runtime.
    Cette étape complète le schéma quand des colonnes ont été ajoutées
    après la première création de la base locale.
    """
    # Migrations runtime limitées à SQLite dev.
    # En PostgreSQL, préférer des migrations versionnées (Alembic) pour éviter
    # les divergences de syntaxe et garder un schéma maîtrisé.
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

        if "voicemails" in table_names:
            cols = {col["name"] for col in inspector.get_columns("voicemails")}
            if "customer_id" in cols and "client_id" not in cols:
                conn.execute(text("ALTER TABLE voicemails RENAME COLUMN customer_id TO client_id"))
                logger.info("Migration légère appliquée: voicemails.customer_id -> voicemails.client_id")

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


def get_db() -> Session:
    """
    Fournit une session de base de données synchrone.
    
    Raises:
        RuntimeError: si la base n'a pas encore été initialisée.
    """
    if SessionLocal is None:
        raise RuntimeError("Base de données non initialisée")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


