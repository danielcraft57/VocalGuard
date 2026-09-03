"""
Client HTTP vers le service OSINT distant (vocalguard-osint sur node15).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from loguru import logger


async def scan_phone_remote(
    base_url: str,
    phone_number: str,
    *,
    token: Optional[str] = None,
    timeout_sec: float = 90.0,
) -> Dict[str, Any]:
    """
    Demande un scan OSINT au worker distant.

    @param base_url URL de base (ex. http://node15.lan:8110).
    @param phone_number Numero a enrichir.
    @param token Token X-OSINT-Token optionnel.
    @param timeout_sec Delai max requete.
    @returns Dict compatible merge OSINT (sources, carrier, country…).
    @raises httpx.HTTPError Si le service est injoignable ou en erreur.
    """
    headers: dict[str, str] = {}
    if token:
        headers["X-OSINT-Token"] = token

    url = f"{base_url.rstrip('/')}/v1/scan"
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.post(
            url,
            json={"phone_number": phone_number},
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()

    # Ne pas remonter le raw complet dans le profil (trop gros) sauf besoin debug
    result = {
        "sources": payload.get("sources") or ["phoneinfoga_remote"],
        "carrier": payload.get("carrier"),
        "country": payload.get("country"),
        "region": payload.get("region"),
        "city": payload.get("city"),
        "postal_code": payload.get("postal_code"),
        "line_type": payload.get("line_type"),
        "social_media": payload.get("social_media") or {},
    }
    # Compat champs VocalGuard
    if payload.get("e164"):
        result["phone_number"] = payload["e164"]
    logger.debug(
        "OSINT distant OK {} -> country={} city={}",
        phone_number,
        result.get("country"),
        result.get("city"),
    )
    return result


async def check_osint_service_health(base_url: str, timeout_sec: float = 3.0) -> bool:
    """
    Verifie que le worker OSINT repond et que PhoneInfoga est pret.

    @param base_url URL de base du service.
    @returns True si /health indique phoneinfoga_ready.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            r = await client.get(f"{base_url.rstrip('/')}/health")
            if r.status_code != 200:
                return False
            body = r.json()
            return bool(body.get("phoneinfoga_ready"))
    except Exception as exc:
        logger.debug("OSINT distant health KO: {}", exc)
        return False
