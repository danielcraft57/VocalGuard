"""
Routes API pour exposer la configuration metier au frontend.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from backend.api.dependencies import get_config
from backend.api.models import (
    IncomingCallConfigPatch,
    IncomingCallConfigResponse,
    IncomingLineModeUpdate,
    SettingsResponse,
    TelephonyStatusResponse,
)
from backend.core.config import Config
from backend.core.incoming_call_settings import (
    apply_incoming_call_settings,
    load_incoming_call_settings,
    patch_incoming_call_settings,
)
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
        if cm.config is not config:
            apply_incoming_line_mode(cm.config, applied)  # type: ignore[arg-type]
    if cm is not None and hasattr(cm, "_refresh_instant_ring_seize"):
        cm._refresh_instant_ring_seize()
    _reload_call_manager_policy(request, config)
    save_incoming_line_mode(config)
    logger.info("Mode ligne entrante bascule: {}", applied)
    return _settings_payload(config)


def _incoming_call_payload(config: Config) -> IncomingCallConfigResponse:
    """
    Construit la config appels entrants effective pour le frontend.

    @param config Configuration live.
    @returns Payload API complet.
    """
    settings = load_incoming_call_settings(config)
    return IncomingCallConfigResponse(
        incoming_line_mode=resolve_incoming_line_mode(config),
        cid_wait_sec=float(settings.cid_wait_sec),
        instant_seize_cid_grace_sec=float(settings.instant_seize_cid_grace_sec),
        ring_cycle_sec=float(settings.ring_cycle_sec),
        ring_quiet_abort_sec=float(settings.ring_quiet_abort_sec),
        max_incoming_wait_sec=float(settings.max_incoming_wait_sec),
        phone_mode_rings=int(settings.phone_mode_rings),
        whitelist_ring_only=bool(settings.whitelist_ring_only),
        whitelist_match=settings.whitelist_match,
        screened_when_unknown=bool(settings.screened_when_unknown),
        active_preset=settings.active_preset,
        presets={k: v.model_dump() for k, v in (settings.presets or {}).items()},
        profiles={k: v.model_dump() for k, v in (settings.profiles or {}).items()},
        profile_overrides={
            k: v.model_dump() for k, v in (settings.profile_overrides or {}).items()
        },
        audio=settings.audio.model_dump(),
        voicemail=settings.voicemail.model_dump(),
        number_patterns=settings.number_patterns.model_dump(),
        advanced=settings.advanced.model_dump(),
        rings_before_answer=int(config.rings_before_answer),
        incoming_auto_answer=bool(getattr(config, "incoming_auto_answer", True)),
    )


def _reload_call_manager_policy(request: Request, config: Config) -> None:
    """
    Recharge policy + instant_ring_seize sur le CallManager local.

    @param request Requete FastAPI.
    @param config Configuration.
    """
    cm = getattr(request.app.state, "call_manager", None)
    if cm is None:
        return
    if hasattr(cm, "reload_incoming_policy"):
        cm.reload_incoming_policy()
    elif hasattr(cm, "_refresh_instant_ring_seize"):
        cm._refresh_instant_ring_seize()
    if getattr(cm, "config", None) is not None and cm.config is not config:
        apply_incoming_call_settings(cm.config, load_incoming_call_settings(config))


@router.get("/settings/incoming-call", response_model=IncomingCallConfigResponse)
async def get_incoming_call_settings(
    request: Request,
    config: Config = Depends(get_config),
) -> IncomingCallConfigResponse:
    """
    Retourne la configuration effective des appels entrants (presets, profils, audio).
    """
    if _should_proxy_settings_to_daemon(config, request):
        data = await _proxy_settings_json(
            request, config, "GET", "/api/v1/settings/incoming-call"
        )
        return IncomingCallConfigResponse(**data)
    load_incoming_line_mode(config)
    return _incoming_call_payload(config)


@router.put("/settings/incoming-call", response_model=IncomingCallConfigResponse)
async def put_incoming_call_settings(
    body: IncomingCallConfigPatch,
    request: Request,
    config: Config = Depends(get_config),
) -> IncomingCallConfigResponse:
    """
    Met a jour partiellement la configuration appels entrants (merge profond).
    """
    patch = body.model_dump(exclude_none=True)
    if not patch:
        if _should_proxy_settings_to_daemon(config, request):
            data = await _proxy_settings_json(
                request, config, "GET", "/api/v1/settings/incoming-call"
            )
            return IncomingCallConfigResponse(**data)
        return _incoming_call_payload(config)

    if _should_proxy_settings_to_daemon(config, request):
        data = await _proxy_settings_json(
            request,
            config,
            "PUT",
            "/api/v1/settings/incoming-call",
            patch,
        )
        patch_incoming_call_settings(config, patch)
        return IncomingCallConfigResponse(**data)

    patch_incoming_call_settings(config, patch)
    _reload_call_manager_policy(request, config)
    logger.info("incoming_call settings mis a jour: {}", list(patch.keys()))
    return _incoming_call_payload(config)


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


@router.get("/telephony/status", response_model=TelephonyStatusResponse)
async def get_telephony_status(
    request: Request,
    config: Config = Depends(get_config),
) -> TelephonyStatusResponse:
    """
    Etat modem / daemon pour la pastille topbar (sans autre UI).

    @param request Contexte (CallManager local ou proxy daemon).
    @param config Configuration.
    @returns Snapshot telephonie.
    """
    # Daemon local (processus telephony) uniquement — pas le CallManager API sans modem.
    is_daemon = bool(getattr(request.app.state, "is_vocalguard_telephony_daemon", False))
    cm = getattr(request.app.state, "call_manager", None)
    if is_daemon and cm is not None:
        snap = cm.modem.health_snapshot()
        relay = getattr(request.app.state, "event_relay", None)
        last_decision = None
        if hasattr(cm, "incoming_policy"):
            last_decision = cm.incoming_policy.last_decision_summary
        return TelephonyStatusResponse(
            status="ok" if snap.get("modem_initialized") else "degraded",
            modem_initialized=bool(snap.get("modem_initialized")),
            modem_port=snap.get("modem_port"),
            firmware_ati3=snap.get("firmware_ati3"),
            last_ring_at=snap.get("last_ring_at"),
            last_cid_raw=snap.get("last_cid_raw"),
            last_error=snap.get("last_error"),
            incoming_line_mode=resolve_incoming_line_mode(config),
            in_call=bool(cm.current_call_id),
            relay_failures=int(getattr(relay, "failure_count", 0) or 0),
            daemon_reachable=True,
            last_incoming_decision=last_decision,
        )

    # API principale : proxy vers daemon si configure
    if getattr(config, "use_telephony_daemon", False):
        url = (getattr(config, "telephony_daemon_url", None) or "http://127.0.0.1:8090").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{url}/health")
            data = r.json() if r.content else {}
            return TelephonyStatusResponse(
                status=str(data.get("status") or ("ok" if r.status_code < 500 else "degraded")),
                modem_initialized=bool(data.get("modem_initialized")),
                modem_port=data.get("modem_port"),
                firmware_ati3=data.get("firmware_ati3"),
                last_ring_at=data.get("last_ring_at"),
                last_cid_raw=data.get("last_cid_raw"),
                last_error=data.get("last_error"),
                incoming_line_mode=data.get("incoming_line_mode")
                or resolve_incoming_line_mode(config),
                in_call=bool(data.get("in_call")),
                relay_failures=int(data.get("relay_failures") or 0),
                daemon_reachable=True,
                last_incoming_decision=data.get("last_incoming_decision"),
            )
        except Exception as exc:
            logger.warning("telephony status: daemon injoignable: {}", exc)
            return TelephonyStatusResponse(
                status="unreachable",
                modem_initialized=False,
                incoming_line_mode=resolve_incoming_line_mode(config),
                last_error=str(exc),
                daemon_reachable=False,
            )

    return TelephonyStatusResponse(
        status="local-no-modem",
        modem_initialized=False,
        incoming_line_mode=resolve_incoming_line_mode(config),
        daemon_reachable=None,
    )
