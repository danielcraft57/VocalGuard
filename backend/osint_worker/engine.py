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


def _libphonenumber_meta(phone_number: str) -> Dict[str, Any]:
    """
    Metadonnees hors-ligne via libphonenumber (comme ProspectLab).

    @param phone_number Numero brut ou E.164.
    @returns carrier, city/region, line_type, e164 si parse OK, sinon {}.
    """
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder
        from phonenumbers.phonenumberutil import NumberParseException
    except ImportError:
        return {}
    try:
        num = phonenumbers.parse(phone_number, "FR")
    except NumberParseException:
        return {}
    if not phonenumbers.is_possible_number(num):
        return {}
    nt = phonenumbers.number_type(num)
    labels = {
        phonenumbers.PhoneNumberType.FIXED_LINE: "fixed",
        phonenumbers.PhoneNumberType.MOBILE: "mobile",
        phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
        phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium",
        phonenumbers.PhoneNumberType.VOIP: "voip",
        phonenumbers.PhoneNumberType.UNKNOWN: None,
    }
    loc = geocoder.description_for_number(num, "fr") or geocoder.description_for_number(num, "en")
    carrier_name = carrier.name_for_number(num, "fr") or carrier.name_for_number(num, "en")
    e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
    out: Dict[str, Any] = {
        "sources": ["libphonenumber"],
        "e164": e164,
        "valid": phonenumbers.is_valid_number(num),
        "line_type": labels.get(nt),
        "carrier": carrier_name or None,
    }
    if loc:
        # Fixe FR : souvent un departement / ville ; mobile : "France"
        if loc.lower() in ("france", "fr"):
            out["country"] = "FR"
        else:
            out["region"] = loc
            out["city"] = loc
            out["country"] = "FR"
    return {k: v for k, v in out.items() if v is not None and v is not False}


async def lookup_company(query: str) -> Dict[str, Any]:
    """
    Recherche une entreprise via l'API publique recherche-entreprises (data.gouv).

    @param query Nom, SIREN, SIRET ou texte libre.
    @returns Champs company_* normalises, ou {}.
    @example
        await lookup_company("Orange")
    """
    q = (query or "").strip()
    if len(q) < 2:
        return {}
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": q, "per_page": 3}
    headers = {
        "Accept": "application/json",
        "User-Agent": "VocalGuard-OSINT/1.0 (LAN)",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200:
                logger.warning("Sirene publique HTTP {}: {}", r.status_code, r.text[:200])
                return {}
            data = r.json()
    except Exception as exc:
        logger.warning("Sirene publique KO: {}", exc)
        return {}
    results = data.get("results") if isinstance(data, dict) else None
    if not results:
        return {}
    first = results[0] if isinstance(results[0], dict) else {}
    siege = first.get("siege") if isinstance(first.get("siege"), dict) else {}
    name = first.get("nom_complet") or first.get("nom_raison_sociale")
    addr_parts = [
        siege.get("adresse") or siege.get("geo_adresse"),
        siege.get("code_postal"),
        siege.get("libelle_commune"),
    ]
    address = ", ".join(str(p) for p in addr_parts if p)
    return {
        "sources": ["sirene_public"],
        "is_company": True,
        "company_name": name,
        "name": name,
        "company_siren": first.get("siren"),
        "company_siret": siege.get("siret"),
        "company_activity": first.get("activite_principale"),
        "company_address": address or None,
        "city": siege.get("libelle_commune"),
        "postal_code": siege.get("code_postal"),
        "region": siege.get("departement"),
        "raw": {"sirene": first},
    }


def prospectlab_configured() -> bool:
    """
    Indique si le worker peut interroger ProspectLab (URL + token).

    @returns True si PROSPECTLAB_API_TOKEN est pose.
    """
    return bool((os.environ.get("PROSPECTLAB_API_TOKEN") or "").strip())


def prospectlab_base_url() -> str:
    """
    URL de base ProspectLab (meme machine, port 5000 par defaut).

    @returns URL sans slash final.
    """
    return (
        (os.environ.get("PROSPECTLAB_URL") or "").strip().rstrip("/")
        or "http://127.0.0.1:5000"
    )


def _map_prospectlab_entreprise(ent: Dict[str, Any], match: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Normalise une fiche ProspectLab vers les champs company_* VocalGuard.

    @param ent Dict entreprise renvoye par l'API publique.
    @param match Infos de matching telephone (optionnel).
    @returns Dict mergeable (is_company, company_name, …).
    """
    name = (
        ent.get("nom")
        or ent.get("raison_sociale")
        or ent.get("nom_complet")
        or ent.get("name")
    )
    addr_parts = [
        ent.get("adresse") or ent.get("street_address"),
        ent.get("code_postal") or ent.get("postal_code"),
        ent.get("ville") or ent.get("locality"),
    ]
    address = ", ".join(str(p) for p in addr_parts if p) or None
    website = (ent.get("site_web") or ent.get("website") or "").strip() or None
    social: Dict[str, Any] = {}
    if website:
        social["website"] = website
    out: Dict[str, Any] = {
        "sources": ["prospectlab"],
        "is_company": True,
        "company_name": name,
        "name": name,
        "company_siren": ent.get("siren"),
        "company_siret": ent.get("siret"),
        "company_activity": ent.get("activite") or ent.get("secteur") or ent.get("naf"),
        "company_address": address,
        "city": ent.get("ville") or ent.get("locality"),
        "postal_code": ent.get("code_postal") or ent.get("postal_code"),
        "social_media": social,
        "raw": {
            "prospectlab_id": ent.get("id"),
            "match": match,
        },
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def lookup_prospectlab_by_phone(phone_number: str) -> Dict[str, Any]:
    """
    Retrouve une entreprise deja connue dans ProspectLab (API publique by-phone).

    @param phone_number Numero E.164 ou local.
    @returns Fiche company_* ou {}.
    """
    token = (os.environ.get("PROSPECTLAB_API_TOKEN") or "").strip()
    if not token or not (phone_number or "").strip():
        return {}
    url = f"{prospectlab_base_url()}/api/public/entreprises/by-phone"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "VocalGuard-OSINT/1.0",
    }
    params = {"phone": phone_number.strip()}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url, headers=headers, params=params)
            if r.status_code == 404:
                return {}
            if r.status_code != 200:
                logger.warning("ProspectLab by-phone HTTP {}: {}", r.status_code, r.text[:200])
                return {}
            payload = r.json()
    except Exception as exc:
        logger.warning("ProspectLab by-phone KO: {}", exc)
        return {}
    if not isinstance(payload, dict) or not payload.get("success"):
        return {}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    ent = data.get("entreprise") if isinstance(data.get("entreprise"), dict) else {}
    if not ent:
        return {}
    mapped = _map_prospectlab_entreprise(ent, data.get("match") if isinstance(data.get("match"), dict) else None)
    if mapped.get("company_name") or mapped.get("company_siren"):
        return mapped
    return {}


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
        "is_company": False,
        "company_name": None,
        "company_siren": None,
        "company_siret": None,
        "company_activity": None,
        "company_address": None,
        "name": None,
        "social_media": {},
        "reputation_links": [],
        "raw": {},
    }

    parsed = phone_number if str(phone_number).startswith("+") else f"+{digits}"
    libmeta = _libphonenumber_meta(parsed)
    if libmeta:
        out["raw"]["libphonenumber"] = libmeta
        for src in libmeta.get("sources") or []:
            if src not in out["sources"]:
                out["sources"].append(src)
        for key in ("e164", "carrier", "country", "region", "city", "line_type"):
            if libmeta.get(key) and not out.get(key):
                out[key] = libmeta[key]

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

    pl = await lookup_prospectlab_by_phone(out.get("e164") or phone_number)
    if pl:
        for src in pl.get("sources") or []:
            if src not in out["sources"]:
                out["sources"].append(src)
        out["is_company"] = True
        for key in (
            "company_name",
            "name",
            "company_siren",
            "company_siret",
            "company_activity",
            "company_address",
            "city",
            "postal_code",
        ):
            if pl.get(key) and not out.get(key):
                out[key] = pl[key]
        if pl.get("social_media"):
            out["social_media"].update(pl["social_media"])
        out["raw"]["prospectlab"] = pl.get("raw") or {}

    # Sirene publique : recherche par numero national FR (09 chiffres locaux)
    if not out.get("company_name") and digits.startswith("33") and len(digits) == 11:
        national = "0" + digits[2:]
        sirene = await lookup_company(national)
        if sirene.get("company_name"):
            out["is_company"] = True
            for src in sirene.get("sources") or []:
                if src not in out["sources"]:
                    out["sources"].append(src)
            for key in (
                "company_name",
                "name",
                "company_siren",
                "company_siret",
                "company_activity",
                "company_address",
                "city",
                "postal_code",
                "region",
            ):
                if sirene.get(key) and not out.get(key):
                    out[key] = sirene[key]
            out["raw"]["sirene_public"] = sirene.get("raw") or {}

    return out
