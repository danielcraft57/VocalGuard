"""
Providers de reputation telephonique pour le worker OSINT (node15).

Sources branchables (cles optionnelles dans .env.osint) :
- HUHU (FR) : Hiya + Truecaller + Orange
- Tellows : score 1-9 (API partenaire ou page publique)
- SpamCalls.net : risque spam communautaire
- Spam-Numbers B2B : agregateur Hiya/spamcalls
- IPQualityScore : fraud_score / spammer / VOIP
- PhoneIntel CLI : Tellows + SpamCalls + c-qui.fr
- truecallerpy : reverse lookup (session locale)

Sans cle API, Tellows (HTML) + SpamCalls restent actifs.
"""

from __future__ import annotations

import asyncio
import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

_UA = "VocalGuard-OSINT/1.1 (+LAN; reputation)"


def _env(name: str) -> str:
    """Lit une variable d'environnement trimmee."""
    return (os.environ.get(name) or "").strip()


def _digits_e164(phone: str) -> str:
    """
    Normalise en E.164 (+chiffres).

    @param phone Numero brut.
    @returns Ex. +33612345678 ou chaine vide.
    """
    cleaned = re.sub(r"[^\d+]", "", (phone or "").strip())
    if not cleaned:
        return ""
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 10:
        cleaned = "+33" + cleaned[1:]
    elif cleaned.startswith("+"):
        pass
    elif cleaned.startswith("33") and len(cleaned) >= 11:
        cleaned = "+" + cleaned
    else:
        cleaned = "+" + cleaned
    return cleaned


def _digits_only(phone: str) -> str:
    """Chiffres seuls (sans +)."""
    return re.sub(r"\D", "", _digits_e164(phone))


def providers_status() -> Dict[str, Any]:
    """
    Etat des providers (pour /health).

    @returns Dict name -> {enabled, mode}.
    """
    phoneintel = False
    try:
        import shutil

        phoneintel = bool(shutil.which("phoneintel")) or os.path.isfile(
            "/opt/vocalguard-osint/venv/bin/phoneintel"
        )
    except Exception:
        pass
    truecaller = False
    try:
        import truecallerpy  # noqa: F401

        truecaller = True
    except Exception:
        pass
    return {
        "huhu": {"enabled": bool(_env("HUHU_API_KEY")), "mode": "api"},
        "tellows": {
            "enabled": True,
            "mode": "api" if _env("TELLOWS_API_KEY") else "html",
        },
        "spamcalls": {"enabled": True, "mode": "html"},
        "spam_numbers": {"enabled": bool(_env("SPAM_NUMBERS_API_KEY")), "mode": "api"},
        "ipqs": {"enabled": bool(_env("IPQS_API_KEY")), "mode": "api"},
        "phoneintel": {"enabled": phoneintel, "mode": "cli"},
        "truecaller": {"enabled": truecaller, "mode": "lib"},
    }


# Valeurs HTML parasites (pubs Google, assets) a ne jamais traiter comme spam_type.
_JUNK_SPAM_TYPES = frozenset(
    {
        "image",
        "images",
        "img",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "webp",
        "icon",
        "logo",
        "button",
        "script",
        "style",
        "css",
        "js",
        "score",
        "scoreimage",
        "light",
        "dark",
        "true",
        "false",
        "none",
        "null",
        "undefined",
        "http",
        "https",
        "www",
    }
)


def is_plausible_spam_type(value: Optional[str]) -> bool:
    """
    Indique si une chaine ressemble a une categorie spam (pas un artefact HTML).

    @param value Candidat spam_type.
    @returns True si acceptable pour persistance / flags.
    """
    if value is None:
        return False
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    if len(cleaned) < 2 or len(cleaned) > 64:
        return False
    low = cleaned.lower()
    if low in _JUNK_SPAM_TYPES:
        return False
    if "http://" in low or "https://" in low or "www." in low:
        return False
    if "\\" in cleaned:
        return False
    # Chemins / URLs relatives (//cdn..., /images/...) mais pas "SCAM / arnaque"
    if re.search(r"(?:^|/)\S+\.\w{2,4}(?:\s|$|/)", cleaned) or cleaned.startswith("//") or cleaned.startswith("/"):
        return False
    if re.fullmatch(r"[\d\W_]+", cleaned):
        return False
    return True


def _category_flags(category: Optional[str]) -> Dict[str, bool]:
    """Derive is_spam / is_scam / is_telemarketer / is_commercial depuis une categorie texte."""
    if not is_plausible_spam_type(category):
        return {
            "is_spam": False,
            "is_scam": False,
            "is_telemarketer": False,
            "is_commercial": False,
            "is_robocall": False,
        }
    cat = (category or "").lower()
    flags = {
        "is_spam": False,
        "is_scam": False,
        "is_telemarketer": False,
        "is_commercial": False,
        "is_robocall": False,
    }
    if any(x in cat for x in ("scam", "fraud", "arnaque", "phishing", "extortion")):
        flags["is_scam"] = True
        flags["is_spam"] = True
    if any(x in cat for x in ("telemarket", "sales", "commercial", "démarch", "demarch", "survey")):
        flags["is_telemarketer"] = True
        flags["is_commercial"] = True
        flags["is_spam"] = True
    if any(x in cat for x in ("robocall", "robot", "automated")):
        flags["is_robocall"] = True
        flags["is_spam"] = True
    if "spam" in cat or "nuisance" in cat or "unwanted" in cat:
        flags["is_spam"] = True
    return flags


def _empty() -> Dict[str, Any]:
    return {}


async def check_huhu(phone: str) -> Dict[str, Any]:
    """
    HUHU.fr SpamChecker (Hiya + Truecaller + Orange).

    @param phone Numero E.164 ou local.
    @returns Dict reputation mergeable ou {}.
    """
    key = _env("HUHU_API_KEY")
    if not key:
        return _empty()
    e164 = _digits_e164(phone)
    if not e164:
        return _empty()
    base = _env("HUHU_API_URL") or "https://num.huhu.fr/api"
    url = f"{base.rstrip('/')}/check/{e164}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                url,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": _UA},
            )
            if r.status_code != 200:
                logger.warning("HUHU HTTP {} pour {}", r.status_code, e164)
                return _empty()
            body = r.json()
    except Exception as exc:
        logger.warning("HUHU KO: {}", exc)
        return _empty()

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return _empty()
    huhu = data.get("huhu") if isinstance(data.get("huhu"), dict) else {}
    truecaller = data.get("truecaller") if isinstance(data.get("truecaller"), dict) else {}
    orange = data.get("orange") if isinstance(data.get("orange"), dict) else {}
    spam_type = (
        huhu.get("spamType")
        or truecaller.get("spamType")
        or orange.get("mainSpamType")
        or ""
    )
    flags = _category_flags(str(spam_type))
    is_spam = bool(huhu.get("isSpam") or orange.get("isSpam") or flags["is_spam"])
    score = huhu.get("spamScore")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None
    if score_f is not None and score_f >= 50:
        is_spam = True
    if score_f is not None and score_f >= 80:
        flags["is_scam"] = flags["is_scam"] or "scam" in str(spam_type).lower()
    reputation = "low" if is_spam or flags["is_scam"] else "high"
    if score_f is not None and 30 <= score_f < 50 and not is_spam:
        reputation = "neutral"
    conf = 0.85 if is_spam else 0.7
    if score_f is not None:
        conf = min(0.95, 0.5 + score_f / 200.0)
    out: Dict[str, Any] = {
        "sources": ["huhu"],
        "reputation": reputation,
        "is_spam": is_spam,
        "is_scam": flags["is_scam"] or bool(orange.get("mainSpamType") == "SCAM"),
        "is_telemarketer": flags["is_telemarketer"] or str(spam_type).lower() in ("sales", "telemarketing"),
        "is_commercial": flags["is_commercial"] or flags["is_telemarketer"],
        "is_robocall": flags["is_robocall"],
        "confidence": conf,
        "spam_type": spam_type or None,
        "spam_score": score_f,
        "carrier": huhu.get("carrier"),
        "line_type": huhu.get("numberType") or huhu.get("lineType"),
        "country": huhu.get("countryCode"),
        "raw": {"huhu": data},
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def check_tellows(phone: str) -> Dict[str, Any]:
    """
    Tellows score 1 (fiable) .. 9 (douteux).

    Prefere l'API partenaire si TELLOWS_API_KEY (+ TELLOWS_PARTNER), sinon page HTML FR/DE.

    @param phone Numero.
    @returns Dict reputation ou {}.
    """
    digits = _digits_only(phone)
    if not digits:
        return _empty()
    api_key = _env("TELLOWS_API_KEY")
    partner = _env("TELLOWS_PARTNER") or "test"
    if api_key:
        host = _env("TELLOWS_API_HOST") or "www.tellows.fr"
        url = f"https://{host}/basic/num/{digits}"
        params = {"xml": "1", "partner": partner, "apikey": api_key}
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                r = await client.get(url, params=params, headers={"User-Agent": _UA})
                if r.status_code == 200 and r.text.strip().startswith("<"):
                    return _parse_tellows_xml(r.text, digits)
        except Exception as exc:
            logger.warning("Tellows API KO, fallback HTML: {}", exc)

    # HTML public
    for host in ("www.tellows.fr", "www.tellows.de", "www.tellows.com"):
        url = f"https://{host}/num/{digits}"
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": _UA, "Accept-Language": "fr,en;q=0.8"})
                if r.status_code != 200:
                    continue
                parsed = _parse_tellows_html(r.text, digits, url)
                if parsed:
                    return parsed
        except Exception as exc:
            logger.debug("Tellows HTML {} KO: {}", host, exc)
    return _empty()


def _parse_tellows_xml(xml_text: str, digits: str) -> Dict[str, Any]:
    """Parse la reponse XML Tellows."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return _empty()
    score_el = root.find(".//score")
    score = None
    if score_el is not None and score_el.text:
        try:
            score = int(score_el.text.strip())
        except ValueError:
            score = None
    caller_types = []
    for el in root.findall(".//callertype") + root.findall(".//types/type"):
        if el is not None and (el.text or "").strip():
            caller_types.append(el.text.strip())
    name_el = root.find(".//callername") or root.find(".//name")
    name = name_el.text.strip() if name_el is not None and name_el.text else None
    return _tellows_result(score, caller_types, name, digits, "api")


def _parse_tellows_html(html: str, digits: str, url: str) -> Dict[str, Any]:
    """Extrait score / categorie depuis la page HTML Tellows."""
    score = None
    for pat in (
        # Nouveau format : /images/score/s5.jpg + class scoreimage
        r"/images/score/s([1-9])\.(?:jpg|jpeg|png|webp)",
        r"/images/score/score([1-9])\.(?:png|jpg|jpeg|webp)",
        r'class="[^"]*scoreimage[^"]*"[^>]+src="[^"]*s([1-9])\.',
        r"tellows\s*(?:Note|Score)\s*(?:pour[^:]{0,40}:\s*)?Score\s*([1-9])\b",
        r'tellows\s*Score\s*([1-9])\b',
        r'alt=["\'][^"\']*Score\s*([1-9])',
    ):
        m = re.search(pat, html, re.I)
        if m:
            score = int(m.group(1))
            break
    categories: List[str] = []
    # Ne pas utiliser data-type= (souvent "image" pour les pubs Google).
    for pat in (
        r'class="[^"]*callertype[^"]*"[^>]*>([^<]{2,60})<',
        r'id="[^"]*callertype[^"]*"[^>]*>([^<]{2,60})<',
        r'(?:Type\s*d.?appel|Call\s*type|Art\s*des\s*Anrufs)\s*[:\-]\s*([^<\n]{2,60})',
    ):
        for hit in re.finditer(pat, html, re.I):
            val = re.sub(r"\s+", " ", hit.group(1)).strip()
            if not is_plausible_spam_type(val):
                continue
            if "tellows" in val.lower():
                continue
            if val not in categories:
                categories.append(val)
    name = None
    nm = re.search(r'class="[^"]*callername[^"]*"[^>]*>([^<]{2,80})<', html, re.I)
    if nm:
        cand = re.sub(r"\s+", " ", nm.group(1)).strip()
        if cand and "http" not in cand.lower() and is_plausible_spam_type(cand):
            name = cand
        elif cand and "http" not in cand.lower() and len(cand) >= 2:
            # Un nom propre n'est pas un spam_type ; on accepte hors filtre junk strict
            if cand.lower() not in _JUNK_SPAM_TYPES and "/" not in cand:
                name = cand
    out = _tellows_result(score, categories, name, digits, "html")
    if out:
        out.setdefault("raw", {})["tellows_url"] = url
    return out


def _tellows_result(
    score: Optional[int],
    categories: List[str],
    name: Optional[str],
    digits: str,
    mode: str,
) -> Dict[str, Any]:
    """Construit le dict mergeable Tellows."""
    categories = [c for c in categories if is_plausible_spam_type(c)]
    if score is None and not categories and not name:
        return _empty()
    cat = categories[0] if categories else None
    flags = _category_flags(" ".join(categories))
    # Score tellows : 1 fiable ... 9 tres douteux (seuil spam >= 6)
    is_spam = bool(score is not None and score >= 6) or flags["is_spam"]
    is_scam = bool(score is not None and score >= 8) or flags["is_scam"]
    if is_spam or is_scam:
        reputation = "low"
    elif score is not None and score <= 3:
        reputation = "high"
    elif score is not None:
        reputation = "neutral"
    else:
        reputation = "neutral"
    conf = 0.55
    if score is not None:
        conf = min(0.95, 0.4 + abs(score - 5) * 0.08)
    out: Dict[str, Any] = {
        "sources": [f"tellows_{mode}"],
        "reputation": reputation,
        "is_spam": is_spam,
        "is_scam": is_scam,
        "is_telemarketer": flags["is_telemarketer"],
        "is_commercial": flags["is_commercial"] or flags["is_telemarketer"],
        "is_robocall": flags["is_robocall"],
        "confidence": conf,
        "spam_score": float(score) if score is not None else None,
        "spam_type": cat if is_plausible_spam_type(cat) else None,
        "name": name,
        "raw": {"tellows_score": score, "tellows_types": categories, "digits": digits},
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


def _spamcalls_page_matches(html: str, final_url: str, digits: str) -> bool:
    """
    Verifie que la page SpamCalls concerne bien le numero demande.

    Le site redirige parfois vers un autre numero proche : on refuse alors le resultat.

    @param html Corps HTML.
    @param final_url URL apres redirects.
    @param digits Chiffres du numero cible.
    @returns True si la page correspond.
    """
    if not digits:
        return False
    candidates: List[str] = []
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if h1:
        candidates.append(re.sub(r"\D", "", h1.group(1)))
    url_m = re.search(r"/num(?:ber)?/(\+?\d+)", final_url or "", re.I)
    if url_m:
        candidates.append(re.sub(r"\D", "", url_m.group(1)))
    title = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if title:
        tm = re.search(r"(\+?\d[\d\s\-]{6,}\d)", title.group(1))
        if tm:
            candidates.append(re.sub(r"\D", "", tm.group(1)))
    for cand in candidates:
        if not cand:
            continue
        if cand == digits or cand.endswith(digits) or digits.endswith(cand):
            return True
    return False


async def check_spamcalls(phone: str) -> Dict[str, Any]:
    """
    SpamCalls.net (page publique).

    @param phone Numero.
    @returns Dict reputation ou {}.
    """
    e164 = _digits_e164(phone)
    digits = _digits_only(phone)
    if not digits:
        return _empty()
    urls = [
        f"https://spamcalls.net/en/number/{e164.lstrip('+')}",
        f"https://spamcalls.net/en/num/{digits}",
        f"https://spamcalls.net/fr/number/{digits}",
        f"https://spamcalls.net/fr/num/{digits}",
    ]
    html = ""
    used = ""
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            for url in urls:
                r = await client.get(url, headers={"User-Agent": _UA, "Accept-Language": "en,fr;q=0.8"})
                if r.status_code != 200 or len(r.text) < 200:
                    continue
                final = str(r.url)
                if not _spamcalls_page_matches(r.text, final, digits):
                    logger.info(
                        "SpamCalls page hors-cible pour {} (final={})",
                        digits,
                        final,
                    )
                    continue
                html = r.text
                used = final
                break
    except Exception as exc:
        logger.warning("SpamCalls KO: {}", exc)
        return _empty()
    if not html:
        return _empty()

    risk = None
    # UI actuelle : <h3>Spam-Risk</h3> ... >High <span>(2 User Reports)</span>
    m = re.search(
        r"Spam[\s\-]?Risk</h3>\s*<h4[^>]*>\s*<a[^>]*>\s*(Low|Medium|High|None|Élevé|Eleve|Moyen|Faible)\b",
        html,
        re.I,
    )
    if m:
        label = m.group(1).lower()
        risk = {
            "high": "high",
            "élevé": "high",
            "eleve": "high",
            "medium": "medium",
            "moyen": "medium",
            "low": "low",
            "faible": "low",
            "none": "low",
        }.get(label, None)
    if not risk:
        m = re.search(r"spam\s*risk[^<:]*[:\s]+(low|medium|high|none)", html, re.I)
        if m:
            risk = m.group(1).lower()
    if not risk:
        if re.search(r"\bhigh\s*risk\b|\brisk\s*:\s*high\b", html, re.I):
            risk = "high"
        elif re.search(r"\bmedium\s*risk\b", html, re.I):
            risk = "medium"
        elif re.search(r"\blow\s*risk\b|\bno\s*spam\b|\bnot\s*spam\b", html, re.I):
            risk = "low"

    reports = None
    for pat in (
        r"\((\d+)\s*(?:User\s*)?Reports?\)",
        r"\((\d+)\s*Signalements?(?:\s+par\s+des\s+utilisateurs?)?\)",
        r"(\d+)\s*(?:user\s*)?reports?\b",
        r"(\d+)\s*signalements?\b",
    ):
        rm = re.search(pat, html, re.I)
        if rm:
            reports = int(rm.group(1))
            break

    category = None
    cm = re.search(
        r"(?:Most frequently reported|Le plus souvent signalé)[^<]{0,80}</h3>\s*<h4[^>]*>\s*<a[^>]*>([^<]{2,60})<",
        html,
        re.I,
    )
    if cm:
        category = re.sub(r"\s+", " ", cm.group(1)).strip()
    if category and not is_plausible_spam_type(category):
        category = None
    if not category:
        cm = re.search(r"(?:category|catégorie|categorie)\s*[:\-]\s*([^<\n]{2,60})", html, re.I)
        if cm and is_plausible_spam_type(cm.group(1).strip()):
            category = cm.group(1).strip()

    flags = _category_flags(category or "")
    is_spam = risk in ("medium", "high") or (reports or 0) >= 3 or flags["is_spam"]
    is_scam = flags["is_scam"] or (risk == "high" and "scam" in (category or "").lower())
    if risk == "high":
        reputation = "low"
    elif risk == "medium" or is_spam:
        reputation = "low"
    elif risk == "low":
        reputation = "high"
    else:
        if not category and reports is None:
            return _empty()
        reputation = "neutral"
    spam_type = category or risk
    if spam_type and not is_plausible_spam_type(spam_type) and spam_type not in ("low", "medium", "high"):
        spam_type = None
    out: Dict[str, Any] = {
        "sources": ["spamcalls"],
        "reputation": reputation,
        "is_spam": is_spam,
        "is_scam": is_scam,
        "is_telemarketer": flags["is_telemarketer"],
        "is_commercial": flags["is_commercial"] or flags["is_telemarketer"],
        "is_robocall": flags["is_robocall"],
        "confidence": 0.75 if risk == "high" else (0.65 if is_spam else 0.5),
        "spam_type": spam_type,
        "raw": {"spamcalls_url": used, "spam_risk": risk, "reports": reports},
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def check_spam_numbers(phone: str) -> Dict[str, Any]:
    """
    Spam-Numbers.com B2B (agregateur).

    @param phone Numero.
    @returns Dict reputation ou {}.
    """
    key = _env("SPAM_NUMBERS_API_KEY")
    if not key:
        return _empty()
    e164 = _digits_e164(phone)
    if not e164:
        return _empty()
    base = _env("SPAM_NUMBERS_API_URL") or "https://spam-numbers.com"
    url = f"{base.rstrip('/')}/b2b/checkNumber"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.post(
                url,
                json={"number": e164},
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": _UA},
            )
            if r.status_code != 200:
                logger.warning("Spam-Numbers HTTP {}", r.status_code)
                return _empty()
            body = r.json()
    except Exception as exc:
        logger.warning("Spam-Numbers KO: {}", exc)
        return _empty()

    data = body if isinstance(body, dict) else {}
    spam_db = data.get("spamDatabases") if isinstance(data.get("spamDatabases"), dict) else data
    hiya = data.get("hiya") if isinstance(data.get("hiya"), dict) else {}
    verdict = (spam_db.get("verdict") or "").upper()
    risk = (spam_db.get("spamRisk") or "").lower()
    category = spam_db.get("category") or hiya.get("category")
    flags = _category_flags(str(category or ""))
    is_spam = verdict in ("SPAM", "LIKELY_SPAM") or risk in ("medium", "high") or flags["is_spam"]
    is_scam = flags["is_scam"]
    reputation = "low" if is_spam else ("high" if verdict == "SAFE" else "neutral")
    out: Dict[str, Any] = {
        "sources": ["spam_numbers"],
        "reputation": reputation,
        "is_spam": is_spam,
        "is_scam": is_scam,
        "is_telemarketer": flags["is_telemarketer"],
        "is_commercial": flags["is_commercial"] or flags["is_telemarketer"],
        "confidence": 0.8 if is_spam else 0.6,
        "spam_type": category or verdict or risk,
        "raw": {"spam_numbers": data},
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def check_ipqs(phone: str) -> Dict[str, Any]:
    """
    IPQualityScore Phone Validation API.

    @param phone Numero.
    @returns Dict reputation ou {}.
    """
    key = _env("IPQS_API_KEY")
    if not key:
        return _empty()
    e164 = _digits_e164(phone)
    if not e164:
        return _empty()
    url = f"https://ipqualityscore.com/api/json/phone/{key}/{e164}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url, params={"strictness": 1}, headers={"User-Agent": _UA})
            if r.status_code != 200:
                logger.warning("IPQS HTTP {}", r.status_code)
                return _empty()
            data = r.json()
    except Exception as exc:
        logger.warning("IPQS KO: {}", exc)
        return _empty()
    if not isinstance(data, dict) or not data.get("success"):
        return _empty()
    fraud = data.get("fraud_score")
    try:
        fraud_f = float(fraud) if fraud is not None else 0.0
    except (TypeError, ValueError):
        fraud_f = 0.0
    is_spam = bool(data.get("spammer") or data.get("risky") or fraud_f >= 75)
    is_scam = bool(data.get("recent_abuse") and fraud_f >= 85) or fraud_f >= 90
    reputation = "low" if is_spam or is_scam else ("high" if fraud_f < 40 else "neutral")
    out: Dict[str, Any] = {
        "sources": ["ipqs"],
        "reputation": reputation,
        "is_spam": is_spam,
        "is_scam": is_scam,
        "is_commercial": False,
        "is_telemarketer": False,
        "confidence": min(0.95, 0.5 + fraud_f / 200.0),
        "spam_score": fraud_f,
        "carrier": data.get("carrier"),
        "line_type": data.get("line_type"),
        "name": data.get("name") if data.get("name") not in (None, "N/A") else None,
        "country": data.get("country"),
        "city": data.get("city"),
        "region": data.get("region"),
        "raw": {
            "ipqs": {
                "fraud_score": fraud_f,
                "VOIP": data.get("VOIP"),
                "prepaid": data.get("prepaid"),
                "active": data.get("active"),
                "spammer": data.get("spammer"),
            }
        },
    }
    if data.get("VOIP"):
        out["line_type"] = out.get("line_type") or "voip"
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def check_phoneintel(phone: str) -> Dict[str, Any]:
    """
    Lance PhoneIntel CLI (--info) si installe.

    @param phone Numero.
    @returns Dict partiel (carrier / liens / texte brut).
    """
    e164 = _digits_e164(phone)
    if not e164:
        return _empty()
    bin_path = _env("PHONEINTEL_BIN") or "phoneintel"
    venv_bin = "/opt/vocalguard-osint/venv/bin/phoneintel"
    if os.path.isfile(venv_bin):
        bin_path = venv_bin
    try:
        proc = await asyncio.create_subprocess_exec(
            bin_path,
            "--info",
            e164,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45.0)
    except FileNotFoundError:
        return _empty()
    except Exception as exc:
        logger.warning("PhoneIntel KO: {}", exc)
        return _empty()
    text = (stdout or b"").decode("utf-8", errors="replace")
    if proc.returncode not in (0, None) and not text.strip():
        err = (stderr or b"").decode("utf-8", errors="replace")[:300]
        logger.debug("PhoneIntel rc={} err={}", proc.returncode, err)
        return _empty()

    out: Dict[str, Any] = {"sources": ["phoneintel"], "raw": {"phoneintel_cli": text[:2500]}}
    # Heuristiques texte
    for pat, key in (
        (r"(?i)^carrier\s*[:=]\s*(.+)$", "carrier"),
        (r"(?i)^country\s*[:=]\s*(.+)$", "country"),
        (r"(?i)^city\s*[:=]\s*(.+)$", "city"),
        (r"(?i)tellows\s*score\s*[:=]\s*([1-9])\b", "spam_score"),
        (r"(?i)spam\s*risk\s*[:=]\s*(low|medium|high)\b", "spam_type"),
    ):
        m = re.search(pat, text, re.M)
        if m:
            val = m.group(1).strip().splitlines()[0][:80]
            if key == "spam_score":
                try:
                    out[key] = float(val)
                except ValueError:
                    pass
            elif key == "spam_type" and val.lower() in ("low", "medium", "high"):
                out[key] = val.lower()
            elif key != "spam_type":
                out[key] = val
    score = out.get("spam_score")
    risk = str(out.get("spam_type") or "").lower()
    flags = _category_flags(risk)
    if score is not None and score >= 5:
        flags["is_spam"] = True
    if "high" in risk:
        flags["is_spam"] = True
    if flags["is_spam"] or flags["is_scam"]:
        out["reputation"] = "low"
        out["is_spam"] = True
        out["is_scam"] = flags["is_scam"]
        out["is_telemarketer"] = flags["is_telemarketer"]
        out["is_commercial"] = flags["is_commercial"]
        out["confidence"] = 0.7
    # Liens reputation éventuels
    links = re.findall(r"https?://[^\s)\"']+", text)
    if links:
        out["reputation_links"] = links[:10]
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


async def check_truecaller(phone: str) -> Dict[str, Any]:
    """
    truecallerpy si package + installation_id disponibles.

    @param phone Numero.
    @returns Dict name / spam ou {}.
    """
    try:
        import truecallerpy
    except ImportError:
        return _empty()
    e164 = _digits_e164(phone)
    if not e164:
        return _empty()
    installation_id = _env("TRUECALLER_INSTALLATION_ID")
    if not installation_id:
        # Pas de session : on signale juste la disponibilite lib, sans appeler
        logger.debug("truecallerpy installe mais TRUECALLER_INSTALLATION_ID manquant")
        return _empty()
    try:
        # API varie selon versions ; on tente search_phonenumber
        search = getattr(truecallerpy, "search_phonenumber", None) or getattr(
            truecallerpy, "search", None
        )
        if search is None:
            return _empty()
        if asyncio.iscoroutinefunction(search):
            data = await search(installation_id, e164, "FR")
        else:
            data = await asyncio.to_thread(search, installation_id, e164, "FR")
    except TypeError:
        try:
            data = await asyncio.to_thread(search, e164, installation_id)  # type: ignore[misc]
        except Exception as exc:
            logger.warning("Truecaller appel KO: {}", exc)
            return _empty()
    except Exception as exc:
        logger.warning("Truecaller KO: {}", exc)
        return _empty()

    if not isinstance(data, dict):
        return _empty()
    # Formats variables selon truecallerpy
    name = None
    spam_score = None
    spam_type = None
    data_block = data.get("data") if isinstance(data.get("data"), dict) else data
    if isinstance(data_block, list) and data_block:
        data_block = data_block[0] if isinstance(data_block[0], dict) else {}
    if isinstance(data_block, dict):
        name = data_block.get("name") or data_block.get("value")
        spam_info = data_block.get("spamInfo") or data_block.get("spam_info") or {}
        if isinstance(spam_info, dict):
            spam_score = spam_info.get("spamScore") or spam_info.get("score")
            spam_type = spam_info.get("spamType") or spam_info.get("type")
    flags = _category_flags(str(spam_type or ""))
    try:
        score_f = float(spam_score) if spam_score is not None else None
    except (TypeError, ValueError):
        score_f = None
    is_spam = flags["is_spam"] or (score_f is not None and score_f >= 2)
    out: Dict[str, Any] = {
        "sources": ["truecaller"],
        "name": name,
        "reputation": "low" if is_spam else ("neutral" if score_f else "high"),
        "is_spam": is_spam,
        "is_scam": flags["is_scam"],
        "is_telemarketer": flags["is_telemarketer"],
        "is_commercial": flags["is_commercial"] or flags["is_telemarketer"],
        "confidence": 0.75 if is_spam else 0.6,
        "spam_score": score_f,
        "spam_type": spam_type,
        "raw": {"truecaller": data},
    }
    return {k: v for k, v in out.items() if v not in (None, "", {}, [])}


def merge_reputation(base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fusionne un resultat provider dans le dict scan.

    @param base Resultat scan en cours.
    @param new Resultat provider.
    @returns base enrichi.
    """
    if not new:
        return base
    for src in new.get("sources") or []:
        if src not in base.setdefault("sources", []):
            base["sources"].append(src)
    for key in (
        "carrier",
        "country",
        "region",
        "city",
        "line_type",
        "name",
        "spam_score",
    ):
        if new.get(key) and not base.get(key):
            base[key] = new[key]
    if new.get("spam_type") and is_plausible_spam_type(str(new.get("spam_type"))) and not base.get("spam_type"):
        base["spam_type"] = new["spam_type"]
    # Reputation : low gagne
    order = {"low": 0, "neutral": 1, "high": 2, None: 3}
    if order.get(new.get("reputation"), 3) < order.get(base.get("reputation"), 3):
        base["reputation"] = new["reputation"]
    elif not base.get("reputation") and new.get("reputation"):
        base["reputation"] = new["reputation"]
    for flag in ("is_spam", "is_scam", "is_telemarketer", "is_commercial", "is_robocall"):
        if new.get(flag):
            base[flag] = True
    if new.get("confidence"):
        base["confidence"] = max(float(base.get("confidence") or 0), float(new["confidence"]))
    if new.get("reputation_links"):
        links = list(base.get("reputation_links") or [])
        for link in new["reputation_links"]:
            if link not in links:
                links.append(link)
        base["reputation_links"] = links[:20]
    if new.get("raw"):
        base.setdefault("raw", {}).update(new["raw"] if isinstance(new["raw"], dict) else {"extra": new["raw"]})
    return base


async def gather_reputation(phone: str) -> Dict[str, Any]:
    """
    Lance tous les providers actives en parallele et fusionne.

    @param phone Numero a analyser.
    @returns Dict reputation agregé.
    """
    disabled = {x.strip().lower() for x in _env("OSINT_REPUTATION_DISABLE").split(",") if x.strip()}
    tasks = []
    names = []
    mapping = [
        ("huhu", check_huhu),
        ("tellows", check_tellows),
        ("spamcalls", check_spamcalls),
        ("spam_numbers", check_spam_numbers),
        ("ipqs", check_ipqs),
        ("phoneintel", check_phoneintel),
        ("truecaller", check_truecaller),
    ]
    for name, fn in mapping:
        if name in disabled:
            continue
        # Skip providers needing keys when not configured (sauf scrapers)
        if name == "huhu" and not _env("HUHU_API_KEY"):
            continue
        if name == "spam_numbers" and not _env("SPAM_NUMBERS_API_KEY"):
            continue
        if name == "ipqs" and not _env("IPQS_API_KEY"):
            continue
        if name == "truecaller" and not _env("TRUECALLER_INSTALLATION_ID"):
            continue
        if name == "phoneintel":
            status = providers_status().get("phoneintel") or {}
            if not status.get("enabled"):
                continue
        tasks.append(fn(phone))
        names.append(name)

    merged: Dict[str, Any] = {
        "sources": [],
        "reputation": None,
        "is_spam": False,
        "is_scam": False,
        "is_telemarketer": False,
        "is_commercial": False,
        "is_robocall": False,
        "confidence": 0.0,
        "reputation_links": [],
        "raw": {},
    }
    if not tasks:
        return merged

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for name, res in zip(names, results):
        if isinstance(res, Exception):
            logger.warning("Reputation provider {} erreur: {}", name, res)
            continue
        if isinstance(res, dict) and res:
            merged = merge_reputation(merged, res)
            logger.info(
                "Reputation {} -> rep={} spam={} scam={} type={}",
                name,
                res.get("reputation"),
                res.get("is_spam"),
                res.get("is_scam"),
                res.get("spam_type"),
            )
    return merged
