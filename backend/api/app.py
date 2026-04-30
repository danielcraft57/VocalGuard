"""
Application FastAPI principale
"""

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from backend.core.config import Config
from backend.core.call_manager import CallManager
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
    entreprises,
    settings as settings_routes,
    stats as stats_routes,
    block_rules as block_rules_routes,
    realtime,
    agenda_public,
)
from backend.database import database as db_module


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
    app.include_router(appointments.router, prefix="/api/v1", tags=["agenda"])
    app.include_router(quotes.router, prefix="/api/v1", tags=["quotes"])
    app.include_router(customers.router, prefix="/api/v1", tags=["customers"])
    app.include_router(entreprises.router, prefix="/api/v1", tags=["entreprises"])
    app.include_router(settings_routes.router, prefix="/api/v1", tags=["settings"])
    app.include_router(stats_routes.router, prefix="/api/v1", tags=["stats"])
    app.include_router(block_rules_routes.router, prefix="/api/v1", tags=["block-rules"])
    app.include_router(agenda_public.router, prefix="/api/v1", tags=["agenda-public"])
    # WebSocket temps reel (evenements d'appels, modem, etc.)
    app.include_router(realtime.router, tags=["realtime"])
    
    # Dossier qui accueille le front (build statique Next.js copié depuis `frontend/out`)
    # Resolve en absolu pour ne pas dépendre du répertoire de travail au lancement.
    web_root = Path(__file__).resolve().parent.parent / "web"

    # Si un dossier `_next` est présent, on le monte pour servir les assets statiques du front.
    next_static = web_root / "_next"
    if next_static.exists():
        app.mount("/_next", StaticFiles(directory=str(next_static)), name="next-static")
    
    @app.on_event("startup")
    async def on_startup() -> None:
        """Initialise la base de donnees et demarre la surveillance des appels (modem)."""
        await db_module.init_database(config.database_url)

        # Demarrer le gestionnaire d'appels (modem, IVR, blocage) en tache de fond
        db = db_module.SessionLocal()
        call_manager = CallManager(config, db)
        await call_manager.initialize()
        task = asyncio.create_task(call_manager.run())
        app.state.call_manager = call_manager
        app.state.call_manager_task = task
        app.state.call_manager_db = db
        logger.info("Surveillance des appels (modem) demarree")

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        """Arrete la surveillance des appels et ferme la session DB."""
        call_manager = getattr(app.state, "call_manager", None)
        task = getattr(app.state, "call_manager_task", None)
        db = getattr(app.state, "call_manager_db", None)
        if call_manager:
            call_manager.stop()
            logger.info("Gestionnaire d'appels arrete")
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if db:
            try:
                db.close()
            except Exception:
                pass

    def _serve_html(rel_path: str):
        """Sert un fichier HTML du build front s'il existe (sécurisé: sous web_root uniquement)."""
        web_abs = web_root.resolve()
        if not rel_path:
            p = web_abs / "index.html"
        else:
            p = (web_abs / f"{rel_path}.html").resolve()
            if not p.is_file():
                p = (web_abs / rel_path / "index.html").resolve()
            if not p.is_file():
                p = web_abs / "index.html"
        if not p.is_file():
            return None
        try:
            p.resolve().relative_to(web_abs)
        except ValueError:
            return None
        return FileResponse(str(p))

    @app.get("/health", include_in_schema=True)
    async def health():
        """Endpoint de santé"""
        return {"status": "healthy"}

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def root():
        """
        Point d'entrée HTTP principal.
        Sert le front (index.html) si présent, sinon JSON d'info API.
        Accepte GET et HEAD (précharge des liens Next.js).
        """
        index_path = web_root / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {
            "name": "VocalGuard API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs"
        }
    
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_frontend(full_path: str):
        """
        Sert les pages du front (dashboard, calls, etc.) pour les URLs comme
        /dashboard, /calls... et fallback sur index.html pour le SPA.
        """
        if full_path.startswith("api/") or full_path.startswith("_next") or full_path == "docs" or full_path.startswith("redoc") or full_path == "openapi.json" or full_path == "health":
            raise HTTPException(status_code=404, detail="Not Found")
        resp = _serve_html(full_path)
        if resp is not None:
            return resp
        raise HTTPException(status_code=404, detail="Not Found")
    
    logger.info("Application FastAPI créée")
    return app

