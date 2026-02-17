"""
Application FastAPI principale
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from loguru import logger

from backend.core.config import Config
from backend.api.routes import (
    calls,
    callers,
    voicemails,
    config as config_routes,
    osint,
    voice_test,
    appointments,
    quotes,
    customers,
    settings as settings_routes,
)
from backend.database.database import init_database


def create_app(config: Config) -> FastAPI:
    """
    Crée et configure l'application FastAPI
    
    Args:
        config: Configuration de l'application
        
    Returns:
        Application FastAPI configurée
    """
    app = FastAPI(
        title="VocalGuard API",
        description="API REST pour VocalGuard - Système de gestion d'appels avec interface vocale",
        version="1.0.0"
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # À restreindre en production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Inclure les routes
    app.include_router(calls.router, prefix="/api/v1", tags=["calls"])
    app.include_router(callers.router, prefix="/api/v1", tags=["callers"])
    app.include_router(voicemails.router, prefix="/api/v1", tags=["voicemails"])
    app.include_router(config_routes.router, prefix="/api/v1", tags=["config"])
    app.include_router(osint.router, prefix="/api/v1", tags=["osint"])
    app.include_router(voice_test.router, prefix="/api/v1", tags=["voice-test"])
    app.include_router(appointments.router, prefix="/api/v1", tags=["appointments"])
    app.include_router(quotes.router, prefix="/api/v1", tags=["quotes"])
    app.include_router(customers.router, prefix="/api/v1", tags=["customers"])
    app.include_router(settings_routes.router, prefix="/api/v1", tags=["settings"])
    
    # Servir les fichiers statiques de l'interface web
    static_path = Path(__file__).parent.parent / "web" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
    
    @app.on_event("startup")
    async def on_startup() -> None:
        """Initialise la base de donnees au demarrage de l'application."""
        await init_database(config.database_url)
    
    @app.get("/")
    async def root():
        """Point d'entrée - redirige vers l'interface web"""
        index_path = static_path / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {
            "name": "VocalGuard API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs"
        }
    
    @app.get("/health")
    async def health():
        """Endpoint de santé"""
        return {"status": "healthy"}
    
    logger.info("Application FastAPI créée")
    return app

