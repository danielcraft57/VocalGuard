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

    # Engine synchrone
    engine = create_engine(database_url, echo=False)
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
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "appointments" not in table_names:
        return

    columns = {col["name"] for col in inspector.get_columns("appointments")}
    with engine.begin() as conn:
        if "source_call_id" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN source_call_id INTEGER"))
            logger.info("Migration légère appliquée: appointments.source_call_id ajouté")
        if "entreprise_id" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN entreprise_id INTEGER"))
            logger.info("Migration légère appliquée: appointments.entreprise_id ajouté")
        if "agenda_tag" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN agenda_tag VARCHAR(50)"))
            logger.info("Migration légère appliquée: appointments.agenda_tag ajouté")
        if "display_icon" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN display_icon VARCHAR(50)"))
            logger.info("Migration légère appliquée: appointments.display_icon ajouté")
        if "display_color" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN display_color VARCHAR(20)"))
            logger.info("Migration légère appliquée: appointments.display_color ajouté")
        if "is_all_day" not in columns:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN is_all_day BOOLEAN NOT NULL DEFAULT 0"))
            logger.info("Migration légère appliquée: appointments.is_all_day ajouté")


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


