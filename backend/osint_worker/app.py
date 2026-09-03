"""
Service HTTP OSINT VocalGuard (PhoneInfoga sur node15).

Lancement :
  PYTHONPATH=/opt/vocalguard-osint \\
  uvicorn backend.osint_worker.app:app --host 0.0.0.0 --port 8110
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from backend.osint_worker import engine as osint_engine


def _expected_token() -> Optional[str]:
    """Token interne LAN (optionnel en dev)."""
    return (os.environ.get("OSINT_INTERNAL_TOKEN") or "").strip() or None


def _check_token(header: Optional[str]) -> None:
    """
    Verifie le token interne si configure.

    @param header Valeur du header X-OSINT-Token.
    @raises HTTPException Si token invalide.
    """
    expected = _expected_token()
    if not expected:
        return
    if (header or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Token OSINT invalide.")


class ScanRequest(BaseModel):
    """Requete de scan numero."""

    phone_number: str = Field(..., description="Numero E.164 ou local FR.")


class ScanResponse(BaseModel):
    """Reponse normalisee pour VocalGuard."""

    phone_number: str
    e164: Optional[str] = None
    sources: list[str] = Field(default_factory=list)
    carrier: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    line_type: Optional[str] = None
    social_media: Dict[str, Any] = Field(default_factory=dict)
    reputation_links: list[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Demarre PhoneInfoga au boot du service."""
    ok = await osint_engine.ensure_ready()
    if ok:
        logger.info(
            "OSINT worker pret (PhoneInfoga {})",
            osint_engine.phoneinfoga_version() or "?",
        )
    else:
        logger.warning("OSINT worker demarre mais PhoneInfoga indisponible")
    yield
    osint_engine.stop_phoneinfoga()


app = FastAPI(title="VocalGuard OSINT", version="1.0.0", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict:
    """Etat du worker et de PhoneInfoga."""
    ready = osint_engine.is_ready()
    return {
        "status": "ok" if ready else "degraded",
        "phoneinfoga_ready": ready,
        "phoneinfoga_version": osint_engine.phoneinfoga_version(),
        "phoneinfoga_bin": osint_engine.phoneinfoga_bin(),
        "phoneinfoga_api": osint_engine.api_base_url(),
    }


@app.post("/v1/scan", response_model=ScanResponse)
async def scan_phone(
    body: ScanRequest,
    x_osint_token: Optional[str] = Header(None, alias="X-OSINT-Token"),
) -> ScanResponse:
    """
    Enrichit un numero via PhoneInfoga (local, OVH, Google dorks, Numverify si cle).

    @param body Numero a scanner.
    @param x_osint_token Token interne optionnel.
    @returns Resultat normalise.
    """
    _check_token(x_osint_token)
    if not (body.phone_number or "").strip():
        raise HTTPException(status_code=400, detail="phone_number requis.")
    if not osint_engine.is_ready():
        ok = await osint_engine.ensure_ready()
        if not ok:
            raise HTTPException(status_code=503, detail="PhoneInfoga indisponible.")
    result = await osint_engine.scan_number(body.phone_number.strip())
    logger.info(
        "OSINT scan {} -> country={} city={} sources={}",
        body.phone_number,
        result.get("country"),
        result.get("city"),
        result.get("sources"),
    )
    return ScanResponse(**{k: result.get(k) for k in ScanResponse.model_fields})
