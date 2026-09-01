"""Routes authentification UI web (mot de passe partage)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.api.models import UiLoginRequest
from backend.api.dependencies import get_config
from backend.core.config import Config
from backend.services.ui_session_service import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_ui_session_cookie_value,
    derive_ui_session_secret,
    verify_ui_session_cookie_value,
)

router = APIRouter(prefix="/auth/ui", tags=["auth-ui"])


class UiSessionStatus(BaseModel):
    """Etat session UI."""

    authenticated: bool
    ui_password_enabled: bool


def _session_secret(config: Config) -> str:
    explicit = (getattr(config, "ui_session_secret", None) or "").strip()
    if explicit:
        return explicit
    pwd = (getattr(config, "ui_password", None) or "").strip()
    if pwd:
        return derive_ui_session_secret(pwd)
    return ""


@router.post("/login")
async def ui_login(payload: UiLoginRequest, response: Response, config: Config = Depends(get_config)) -> dict:
    """
    Authentifie l utilisateur UI avec VG_UI_PASSWORD et pose un cookie httpOnly.

    @param payload Mot de passe saisi.
    @returns Confirmation de connexion.
    """
    expected = (getattr(config, "ui_password", None) or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Mot de passe UI non configure.")
    if payload.password != expected:
        raise HTTPException(status_code=401, detail="Mot de passe incorrect.")

    secret = _session_secret(config)
    value = create_ui_session_cookie_value(secret)
    response.set_cookie(
        key=COOKIE_NAME,
        value=value,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return {"ok": True, "message": "Connecte."}


@router.post("/logout")
async def ui_logout(response: Response) -> dict:
    """Efface le cookie de session UI."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UiSessionStatus)
async def ui_me(request: Request, config: Config = Depends(get_config)) -> UiSessionStatus:
    """
    Indique si une session UI valide est presente.

    @returns Etat d authentification.
    """
    pwd = (getattr(config, "ui_password", None) or "").strip()
    if not pwd:
        return UiSessionStatus(authenticated=True, ui_password_enabled=False)
    secret = _session_secret(config)
    cookie = request.cookies.get(COOKIE_NAME)
    return UiSessionStatus(
        authenticated=verify_ui_session_cookie_value(secret, cookie),
        ui_password_enabled=True,
    )
