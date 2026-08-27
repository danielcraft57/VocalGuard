"""
Composition root du service telephony (FastAPI + modem + relais evenements).

Separe la construction de l'app (`create_telephony_app`) du point d'entree ASGI (`main.py`).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from backend.api.routes import calls, outgoing_audio, settings as settings_routes
from backend.core.call_manager import CallManager
from backend.core.config import Config
from backend.core.incoming_line_mode import load_incoming_line_mode, resolve_incoming_line_mode
from backend.database import database as db_module
from backend.telephony_daemon.relay_wiring import get_wired_relay, wire_daemon_relay_once


def create_telephony_app(config: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        load_incoming_line_mode(config)
        relay = wire_daemon_relay_once(config)
        app.state.event_relay = relay
        await db_module.init_database(config.database_url)
        db = db_module.SessionLocal()
        call_manager = CallManager(config, db)
        await call_manager.initialize()
        call_manager._refresh_instant_ring_seize()
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
            rel = getattr(app.state, "event_relay", None)
            if cm:
                cm.stop()
                logger.info("Telephony daemon: CallManager arrete")
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
            if rel is not None:
                try:
                    await rel.aclose()
                except Exception:
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
    app.state.is_vocalguard_telephony_daemon = True
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(calls.router, prefix="/api/v1", tags=["calls"])
    app.include_router(outgoing_audio.router, tags=["outgoing-audio"])
    app.include_router(settings_routes.router, prefix="/api/v1", tags=["settings"])

    @app.get("/health")
    async def health() -> JSONResponse:
        """
        Sante daemon : 200 si modem OK, 503 sinon (monitoring / smoke).

        @returns Payload JSON (modem, firmware, relay, mode ligne).
        """
        cm = getattr(app.state, "call_manager", None)
        modem_ok = bool(cm and cm.modem.is_initialized)
        payload: dict[str, Any] = {
            "status": "ok" if modem_ok else "degraded",
            "role": "telephony",
            "modem_initialized": modem_ok,
            "incoming_line_mode": resolve_incoming_line_mode(config) if config else "voicemail",
            "incoming_auto_answer": bool(getattr(config, "incoming_auto_answer", True)),
        }
        if cm:
            payload.update(cm.modem.health_snapshot())
            payload["in_call"] = bool(cm.current_call_id)
            payload["current_call_id"] = cm.current_call_id
        relay = getattr(app.state, "event_relay", None) or get_wired_relay()
        if relay is not None:
            payload.update(relay.health_fields())
        return JSONResponse(payload, status_code=200 if modem_ok else 503)

    return app
