"""
Gestion de la base de données (mode synchrone simple pour le développement).

On utilise un engine SQLAlchemy classique et une seule factory de sessions.
L'initialisation est déclenchée au démarrage de l'application FastAPI.
"""

from sqlalchemy import create_engine, event
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

    logger.info("Base de données initialisée")


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


