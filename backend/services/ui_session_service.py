"""
Service de session cookie pour l'authentification UI web VocalGuard.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

COOKIE_NAME = "vg_ui_session"
SESSION_TTL_SECONDS = 7 * 86400


def derive_ui_session_secret(ui_password: str) -> str:
    """
    Derive un secret HMAC stable a partir du mot de passe UI.

    @param ui_password Mot de passe UI configure.
    @returns Secret hex pour signer les cookies.
    """
    return hashlib.sha256(f"vocalguard-ui:{ui_password}".encode("utf-8")).hexdigest()


def _b64url_encode(raw: bytes) -> str:
    """Encode des octets en base64 URL-safe sans padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    """Decode base64 URL-safe avec padding restaure."""
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_ui_session_cookie_value(secret: str) -> str:
    """
    Cree la valeur signee du cookie de session UI.

    @param secret Secret HMAC.
    @returns Valeur a stocker dans le cookie httpOnly.
    """
    payload = {"exp": int(time.time()) + SESSION_TTL_SECONDS, "v": 1}
    raw = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_ui_session_cookie_value(secret: str, cookie_value: Optional[str]) -> bool:
    """
    Verifie l'integrite et l'expiration d'un cookie de session UI.

    @param secret Secret HMAC partage avec la creation.
    @param cookie_value Valeur lue depuis le cookie client.
    @returns True si la session est valide.
    """
    if not secret or not cookie_value or "." not in cookie_value:
        return False
    raw, sig = cookie_value.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    try:
        payload = json.loads(_b64url_decode(raw).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return False
    exp = int(payload.get("exp") or 0)
    return exp >= int(time.time())
