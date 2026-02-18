"""
Fournisseurs de reputation externe pour les numeros (type callattendant).

- NOMOROBO : USA, API officielle (X-API-Key). Robocalls / spam.
- SHOULDIANSWER : hors USA, communaute ; pas d'API publique officielle pour l'instant (stub).
"""

import re
from typing import Any, Dict, Optional

import httpx
from loguru import logger


NOMOROBO_CHECK_URL = "https://api.nomorobo.com/v2/check"


def _e164_from_phone(phone: str) -> str:
    """Retourne un numero en format E.164 (chiffres avec +)."""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if digits.startswith("33") and len(digits) >= 11:
        return "+" + digits
    if len(digits) == 10 and digits.startswith("0"):
        return "+33" + digits[1:]
    if len(digits) == 11 and digits.startswith("33"):
        return "+" + digits
    if not digits.startswith("+"):
        return "+" + digits
    return "+" + digits


def _is_us_number(e164: str) -> bool:
    """True si le numero est US (E.164 +1)."""
    return e164.startswith("+1") and len(re.sub(r"\D", "", e164)) == 11


async def check_nomorobo(
    phone_number: str,
    api_key: Optional[str] = None,
    to_number: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Interroge l'API Nomorobo (robocalls / spam, USA).

    Args:
        phone_number: Numero appelant (From).
        api_key: X-API-Key (env NOMOROBO_API_KEY).
        to_number: Numero cible (To), optionnel ; defaut +15551234567 pour la requete.

    Returns:
        Dict avec reputation, is_spam, is_robocall, score, sources, etc. Vide si desactive ou erreur.
    """
    if not api_key or not api_key.strip():
        return {}
    e164 = _e164_from_phone(phone_number)
    if not e164 or not _is_us_number(e164):
        logger.debug("Nomorobo: numero non US, ignore")
        return {}
    from_param = e164.replace("+", "")
    to_param = (to_number or "+15551234567").replace("+", "").replace(" ", "")
    if not re.match(r"^\d+$", to_param):
        to_param = "15551234567"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                NOMOROBO_CHECK_URL,
                params={"From": from_param, "To": to_param},
                headers={
                    "X-API-Key": api_key.strip(),
                    "Accept": "application/json",
                },
            )
            if response.status_code != 200:
                logger.warning("Nomorobo API: status {} pour {}", response.status_code, phone_number)
                return {}
            data = response.json()
            # Reponse typique: score 1 = robocall, 0 = ok ; ou champs type/risk
            score = data.get("score") if isinstance(data.get("score"), (int, float)) else None
            if score is None:
                score = data.get("risk", 0)
            is_robocall = data.get("is_robocall", score == 1 if score is not None else False)
            if score is not None and score >= 0.5 and not isinstance(is_robocall, bool):
                is_robocall = True
            reputation = "low" if is_robocall else "high"
            return {
                "sources": ["nomorobo"],
                "reputation": reputation,
                "is_spam": bool(is_robocall),
                "is_scam": bool(data.get("is_scam", False)),
                "is_robocall": bool(is_robocall),
                "confidence": 0.9 if is_robocall else 0.7,
                "score": score,
            }
    except Exception as e:
        logger.warning("Nomorobo: erreur pour {}: {}", phone_number, e)
    return {}


async def check_shouldianswer(
    phone_number: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stub pour Should I Answer (hors USA, communaute).
    Pas d'API publique officielle documentee ; structure prete pour une future integration.

    Args:
        phone_number: Numero a verifier.
        api_key: Cle API si un service tiers est utilise plus tard.

    Returns:
        Dict vide pour l'instant (reputation inconnue).
    """
    if not api_key or not api_key.strip():
        logger.debug("ShouldIAnswer: pas de cle API configuree")
        return {}
    # TODO: integrer un endpoint si disponible (ex. partenaire ou API communaute)
    logger.debug("ShouldIAnswer: lookup non implemente pour {}", phone_number)
    return {}


def should_block_from_reputation_result(result: Dict[str, Any]) -> bool:
    """
    Indique si un resultat de fournisseur de reputation recommande le blocage.

    Args:
        result: Dict retourne par check_nomorobo ou check_shouldianswer.

    Returns:
        True si bloquer recommande.
    """
    if not result:
        return False
    if result.get("reputation") == "low":
        return True
    if result.get("is_spam") or result.get("is_scam") or result.get("is_robocall"):
        return True
    return False
