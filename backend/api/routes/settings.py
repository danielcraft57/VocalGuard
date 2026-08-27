"""
Routes API pour exposer la configuration metier au frontend.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from backend.api.dependencies import get_config
from backend.api.models import IncomingLineModeUpdate, SettingsResponse
from backend.core.config import Config
from backend.core.incoming_line_mode import (
    apply_incoming_line_mode,
    load_incoming_line_mode,
    resolve_incoming_line_mode,
    save_incoming_line_mode,
)


router = APIRouter()


def _settings_payload(config: Config) -> SettingsResponse:
    """
    Construit le snapshot settings pour le frontend.

    @param config Configuration live.
    @returns Payload SettingsResponse.
    """
    return SettingsResponse(
        database_url=config.database_url,
        api_host=config.api_host,
        api_port=config.api_port,
        modem_port=config.modem_port,
        voice_language=config.voice_language,
        rings_before_answer=int(config.rings_before_answer),
        voicemail_enabled=bool(config.voicemail_enabled),
        incoming_auto_answer=bool(getattr(config, "incoming_auto_answer", True)),
        incoming_line_mode=resolve_incoming_line_mode(config),
    )


def _should_proxy_settings_to_daemon(config: Config, request: Request) -> bool:
    """
    Proxifie vers le daemon telephonie (config live CallManager) sauf si on y est deja.

    @param config Configuration.
    @param request Requete FastAPI.
    @returns True si proxy requis.
    """
    if getattr(request.app.state, "is_vocalguard_telephony_daemon", False):
        return False
    return bool(config.use_telephony_daemon)


async def _proxy_settings_json(
    request: Request,
    config: Config,
    method: str,
    path: str,
    json_body: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Relais HTTP vers le daemon telephonie.

    @param request Requete entrante.
    @param config Configuration (URL daemon).
    @param method GET ou PUT.
    @param path Chemin API (ex. /api/v1/settings).
    @param json_body Corps JSON optionnel.
    @returns JSON parse.
    """
    base = (
        getattr(request.app.state, "telephony_daemon_url", None) or config.telephony_daemon_url
    )
    url = f"{str(base).strip().rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                r = await client.get(url, timeout=15.0)
            else:
                r = await client.put(url, json=json_body or {}, timeout=15.0)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Daemon telephonie injoignable pour settings: {exc}",
        ) from exc
    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail=(r.text or "Reponse invalide")[:400])
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=data)
    return data


def _apply_live(request: Request, config: Config, mode: str) -> SettingsResponse:
    """
    Applique le mode sur la config du process + CallManager si present, puis persiste.

    @param request App FastAPI (state.call_manager).
    @param config Singleton config.
    @param mode voicemail|phone.
    @returns Snapshot settings.
    """
    applied = apply_incoming_line_mode(config, mode)  # type: ignore[arg-type]
    cm = getattr(request.app.state, "call_manager", None)
    if cm is not None and getattr(cm, "config", None) is not None:
        apply_incoming_line_mode(cm.config, applied)
    save_incoming_line_mode(config)
    logger.info("Mode ligne entrante bascule: {}", applied)
    return _settings_payload(config)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    request: Request,
    config: Config = Depends(get_config),
) -> SettingsResponse:
    """
    Retourne un snapshot de la configuration utile au frontend.
    """
    if _should_proxy_settings_to_daemon(config, request):
        data = await _proxy_settings_json(request, config, "GET", "/api/v1/settings")
        return SettingsResponse(**data)
    # Au premier GET, restaurer le runtime si present (process API sans daemon).
    load_incoming_line_mode(config)
    return _settings_payload(config)


@router.put("/settings/incoming-line-mode", response_model=SettingsResponse)
async def put_incoming_line_mode(
    body: IncomingLineModeUpdate,
    request: Request,
    config: Config = Depends(get_config),
) -> SettingsResponse:
    """
    Bascule répondeur (coupe-sonnerie) / téléphone parallèle.

    @param body Mode cible.
    @param request Contexte app (CallManager daemon).
    @param config Configuration.
    @returns Settings a jour.
    """
    if _should_proxy_settings_to_daemon(config, request):
        data = await _proxy_settings_json(
            request,
            config,
            "PUT",
            "/api/v1/settings/incoming-line-mode",
            {"mode": body.mode},
        )
        # Aligne aussi le singleton API (affichage / persist locale).
        apply_incoming_line_mode(config, body.mode)
        save_incoming_line_mode(config)
        return SettingsResponse(**data)
    return _apply_live(request, config, body.mode)
