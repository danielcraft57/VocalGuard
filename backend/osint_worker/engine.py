"""
Moteur OSINT local : API REST PhoneInfoga (sundowndev) + normalisation.

PhoneInfoga est demarre en sous-processus (serve --no-client) et interroge
via HTTP sur localhost. Les numeros sont envoyes en chiffres seuls (ex. 336…).
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

_phoneinfoga_proc: Optional[subprocess.Popen] = None
_api_base: str = ""
_bin_path: str = ""


def _digits_only(phone_number: str) -> str:
    """
    Normalise un numero pour l'API PhoneInfoga (chiffres uniquement).

    @param phone_number Numero E.164 ou local.
    @returns Chaine de chiffres (ex. 33612345678).
    """
    cleaned = re.sub(r"[^\d+]", "", (phone_number or "").strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    elif cleaned.startswith("00"):
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 10:
        cleaned = "33" + cleaned[1:]
    return cleaned


def phoneinfoga_bin() -> str:
    """
    Chemin du binaire PhoneInfoga Go (pas le faux package pipx).

    @returns Chemin absolu ou nom dans le PATH.
    """
    return (
        (os.environ.get("PHONEINFOGA_BIN") or "").strip()
        or "/opt/vocalguard-osint/bin/phoneinfoga"
    )


def api_base_url() -> str:
    """
    URL de base de l'API PhoneInfoga locale.

    @returns URL sans slash final (ex. http://127.0.0.1:5011).
    """
    return (
        (os.environ.get("PHONEINFOGA_API_URL") or "").strip().rstrip("/")
        or "http://127.0.0.1:5011"
    )


def api_port() -> int:
    """
    Port d'ecoute PhoneInfoga derive de PHONEINFOGA_API_URL.

    @returns Port TCP (defaut 5011).
    """
    base = api_base_url()
    try:
        from urllib.parse import urlparse

        port = urlparse(base).port
        if port:
            return int(port)
    except Exception:
        pass
    return 5011


async def _wait_healthy(timeout_sec: float = 15.0) -> bool:
    """
    Attend que /api/ de PhoneInfoga reponde.

    @param timeout_sec Delai max.
    @returns True si OK.
    """
    url = f"{api_base_url()}/api/"
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get(url)
                if r.status_code == 200 and r.json().get("success"):
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return False


def start_phoneinfoga() -> None:
    """
    Demarre PhoneInfoga serve --no-client si l'API n'est pas deja joignable.

    @raises RuntimeError Si le binaire est introuvable ou le demarrage echoue.
    """
    global _phoneinfoga_proc, _api_base, _bin_path
    _api_base = api_base_url()
    _bin_path = phoneinfoga_bin()
    if not os.path.isfile(_bin_path):
        raise RuntimeError(f"Binaire PhoneInfoga introuvable: {_bin_path}")

    # Deja up (systemd separe ou relance) ?
    try:
        with httpx.Client(timeout=1.0) as client:
            r = client.get(f"{_api_base}/api/")
            if r.status_code == 200 and r.json().get("success"):
                logger.info("PhoneInfoga deja joignable sur {}", _api_base)
                return
    except Exception:
        pass

    port = api_port()
    cmd = [_bin_path, "serve", "--no-client", "-p", str(port)]
    logger.info("Demarrage PhoneInfoga: {}", " ".join(cmd))
    _phoneinfoga_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop_phoneinfoga() -> None:
    """Arrete le sous-processus PhoneInfoga demarre par ce service."""
    global _phoneinfoga_proc
    if _phoneinfoga_proc is None:
        return
    try:
        os.killpg(os.getpgid(_phoneinfoga_proc.pid), signal.SIGTERM)
    except Exception:
        try:
            _phoneinfoga_proc.terminate()
        except Exception:
            pass
    _phoneinfoga_proc = None


async def ensure_ready() -> bool:
    """
    Verifie / demarre PhoneInfoga et attend le healthcheck.

    @returns True si l'API locale est prete.
    """
    try:
        start_phoneinfoga()
    except Exception as exc:
        logger.error("PhoneInfoga demarrage KO: {}", exc)
        return False
    ok = await _wait_healthy()
    if not ok:
        logger.error("PhoneInfoga health timeout sur {}", api_base_url())
    return ok


def is_ready() -> bool:
    """
    Healthcheck synchrone (pour /health).

    @returns True si /api/ repond.
    """
    try:
        with httpx.Client(timeout=1.5) as client:
            r = client.get(f"{api_base_url()}/api/")
            return r.status_code == 200 and bool(r.json().get("success"))
    except Exception:
        return False


def phoneinfoga_version() -> str:
    """
    Version PhoneInfoga si dispo.

    @returns Chaine version ou vide.
    """
    try:
        with httpx.Client(timeout=1.5) as client:
            r = client.get(f"{api_base_url()}/api/")
            if r.status_code == 200:
                body = r.json()
                return str(body.get("version") or "")
    except Exception:
        pass
    return ""


async def _post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    POST JSON vers l'API PhoneInfoga.

    @param path Chemin relatif (ex. /api/v2/numbers).
    @param payload Corps JSON.
    @returns Corps de reponse ou {}.
    """
    url = f"{api_base_url()}{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            logger.warning("PhoneInfoga {} -> {}: {}", path, r.status_code, r.text[:300])
            return {}
        return r.json() if r.content else {}


async def scan_number(phone_number: str) -> Dict[str, Any]:
    """
    Enrichit un numero via PhoneInfoga (local + ovh + googlesearch + numverify si cle).

    @param phone_number Numero a scanner.
    @returns Dict normalise pour VocalGuard (sources, carrier, country, city, social_media…).
    @example
        result = await scan_number("+33612345678")
    """
    digits = _digits_only(phone_number)
    if not digits:
        return {"phone_number": phone_number, "sources": [], "error": "numero vide"}

    out: Dict[str, Any] = {
        "phone_number": phone_number,
        "e164": None,
        "sources": ["phoneinfoga"],
        "carrier": None,
        "country": None,
        "region": None,
        "city": None,
        "postal_code": None,
        "line_type": None,
        "social_media": {},
        "reputation_links": [],
        "raw": {},
    }

    meta = await _post_json("/api/v2/numbers", {"number": digits})
    if meta:
        out["raw"]["numbers"] = meta
        out["e164"] = meta.get("e164") or out["e164"]
        out["country"] = meta.get("country") or out["country"]
        if meta.get("carrier"):
            out["carrier"] = meta.get("carrier")

    scanners: List[str] = ["local", "ovh", "googlesearch"]
    # numverify seulement si cle presente cote PhoneInfoga (.env)
    if (os.environ.get("NUMVERIFY_API_KEY") or "").strip():
        scanners.append("numverify")

    for name in scanners:
        payload = {"number": digits, "options": {}}
        data = await _post_json(f"/api/v2/scanners/{name}/run", payload)
        if not data:
            continue
        out["raw"][name] = data
        result = data.get("result") if isinstance(data, dict) else None
        if not isinstance(result, dict):
            continue

        if name == "local":
            out["e164"] = result.get("e164") or out["e164"]
            out["country"] = result.get("country") or out["country"]
            if result.get("carrier"):
                out["carrier"] = result.get("carrier")

        elif name == "ovh":
            if result.get("found"):
                out["city"] = result.get("city") or out["city"]
                out["postal_code"] = result.get("zip_code") or out["postal_code"]

        elif name == "numverify":
            if result.get("carrier"):
                out["carrier"] = result.get("carrier")
            if result.get("country_name"):
                out["country"] = result.get("country_name")
            if result.get("line_type"):
                out["line_type"] = result.get("line_type")
            if result.get("location"):
                out["region"] = result.get("location")

        elif name == "googlesearch":
            social = {}
            for item in result.get("social_media") or []:
                url = item.get("url") if isinstance(item, dict) else None
                dork = item.get("dork") if isinstance(item, dict) else None
                if url and dork and "facebook" in dork:
                    social["facebook_search"] = url
                elif url and dork and "linkedin" in dork:
                    social["linkedin_search"] = url
                elif url and dork and "instagram" in dork:
                    social["instagram_search"] = url
            if social:
                out["social_media"] = social
            links = []
            for item in result.get("reputation") or []:
                if isinstance(item, dict) and item.get("url"):
                    links.append(item["url"])
            out["reputation_links"] = links[:15]

    return out
