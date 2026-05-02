"""
Composition root du service telephony (FastAPI + modem + relais evenements).

Separe la construction de l'app (`create_telephony_app`) du point d'entree ASGI (`main.py`).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import calls, outgoing_audio
from backend.core.call_manager import CallManager
from backend.core.config import Config
from backend.database import database as db_module
from backend.telephony_daemon.relay_wiring import wire_daemon_relay_once


def create_telephony_app(config: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        wire_daemon_relay_once(config)
        await db_module.init_database(config.database_url)
        db = db_module.SessionLocal()
        call_manager = CallManager(config, db)
        await call_manager.initialize()
        task = asyncio.create_task(call_manager.run())
        app.state.call_manager = call_manager
        app.state.call_manager_task = task
        app.state.call_manager_db = db
        logger.info(
            "Telephony daemon pret (modem={}, relay vers {})",
            call_manager.modem.is_initialized,
            config.telephony_public_api_url,
        )
        try:
            yield
        finally:
            cm = getattr(app.state, "call_manager", None)
            t = getattr(app.state, "call_manager_task", None)
            dbs = getattr(app.state, "call_manager_db", None)
            if cm:
                cm.stop()
                logger.info("Telephony daemon: CallManager arrete")
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            if dbs:
                try:
                    dbs.close()
                except Exception:
                    pass

    app = FastAPI(
        title="VocalGuard Telephony",
        description="Service dedie modem, appels et audio WebSocket (interne)",
        version="0.2",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(calls.router, prefix="/api/v1", tags=["calls"])
    app.include_router(outgoing_audio.router, tags=["outgoing-audio"])

    @app.get("/health")
    async def health() -> dict:
        cm = getattr(app.state, "call_manager", None)
        return {
            "status": "ok",
            "role": "telephony",
            "modem_initialized": bool(cm and cm.modem.is_initialized),
        }

    return app
