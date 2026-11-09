"""
Endpoints KB VocalGuard pour ProspectLab (sans cookie UI).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.api.dependencies import get_config
from backend.api.routes.kb import ChatBody, get_intents, kb_chat
from backend.core.config import Config

router = APIRouter(prefix="/internal", tags=["internal-kb"])


def _check_internal_token(
    config: Config,
    x_vocalguard_internal: Optional[str],
) -> None:
    """
    Verifie le jeton interne si TELEPHONY_INTERNAL_TOKEN est defini.

    @param config: Config VocalGuard
    @param x_vocalguard_internal: Header X-VocalGuard-Internal
    @raises HTTPException: 401 si jeton attendu et incorrect
    """
    expected = (config.telephony_internal_token or "").strip()
    if not expected:
        return
    if (x_vocalguard_internal or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Non autorise")


@router.post("/kb/chat")
async def internal_kb_chat(
    body: ChatBody,
    request: Request,
    x_vocalguard_internal: Optional[str] = Header(None, alias="X-VocalGuard-Internal"),
    config: Config = Depends(get_config),
):
    """
    Tchatche KB (meme logique que /api/v1/kb/chat) pour ProspectLab.

    @param body: Message + historique
    @param request: Requete FastAPI
    @returns: reply, tag, score, top_predictions
    """
    _check_internal_token(config, x_vocalguard_internal)
    return await kb_chat(body, request)


@router.get("/kb/intents")
async def internal_kb_intents(
    request: Request,
    enabled_only: bool = True,
    profile: Optional[str] = "inbound",
    x_vocalguard_internal: Optional[str] = Header(None, alias="X-VocalGuard-Internal"),
    config: Config = Depends(get_config),
):
    """
    Catalogue intents pour les suggestions Messenger ProspectLab.

    @param request: Requete FastAPI
    @param enabled_only: Filtre enabled
    @param profile: inbound | outbound_commercial
    @returns: {intents, count, profile}
    """
    _check_internal_token(config, x_vocalguard_internal)
    return await get_intents(request, enabled_only=enabled_only, profile=profile)
