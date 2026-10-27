"""
Pool multi-clefs ElevenLabs : quotas, reset, auto-switch.

Les clefs viennent de ``ELEVENLABS_API_KEYS`` (csv) et/ou ``ELEVENLABS_API_KEY``.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

_API_BASE = "https://api.elevenlabs.io/v1"
_CACHE_TTL_SEC = 60.0
_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "fetched_at": 0.0,
    "keys": [],  # List[KeyQuota]
    "active_fingerprint": None,
}


@dataclass
class KeyQuota:
    """Etat quota d'une clef ElevenLabs."""

    fingerprint: str
    label: str
    ok: bool
    tier: Optional[str] = None
    status: Optional[str] = None
    character_count: Optional[int] = None
    character_limit: Optional[int] = None
    remaining: Optional[int] = None
    next_reset_unix: Optional[int] = None
    next_reset_iso: Optional[str] = None
    created_at_unix: Optional[int] = None
    created_at_iso: Optional[str] = None
    user_id: Optional[str] = None
    error: Optional[str] = None
    active: bool = False
    quota_readable: bool = True

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialise sans exposer la clef."""
        d = asdict(self)
        return d


def mask_api_key(key: str) -> str:
    """
    Masque une clef pour l'UI (sk_xxxx…yyyy).

    @param key Clef brute.
    @returns Label masque.
    """
    k = (key or "").strip()
    if len(k) < 12:
        return "sk_***"
    return f"{k[:6]}…{k[-4:]}"


def key_fingerprint(key: str) -> str:
    """
    Empreinte courte stable (pas reversible).

    @param key Clef.
    @returns Hex 12 car.
    """
    import hashlib

    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:12]


def parse_api_keys_from_env() -> List[str]:
    """
    Lit ``ELEVENLABS_API_KEYS`` (csv / lignes) + ``ELEVENLABS_API_KEY``.

    @returns Liste unique ordonnee.
    """
    raw_multi = (os.environ.get("ELEVENLABS_API_KEYS") or "").strip()
    raw_single = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    keys: List[str] = []
    if raw_multi:
        for part in raw_multi.replace("\n", ",").replace(";", ",").split(","):
            k = part.strip()
            if k and k not in keys:
                keys.append(k)
    if raw_single and raw_single not in keys:
        # Clef "principale" en tete si absente du pool.
        keys.insert(0, raw_single)
    return keys


def _http_json(url: str, api_key: str, timeout: float = 20.0) -> Dict[str, Any]:
    """GET JSON ElevenLabs."""
    req = urllib.request.Request(
        url,
        headers={
            "xi-api-key": api_key,
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _iso_from_unix(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def fetch_key_quota(api_key: str) -> KeyQuota:
    """
    Interroge ``/v1/user`` (+ subscription) pour une clef.

    @param api_key Clef xi-api-key.
    @returns Quota.
    """
    fp = key_fingerprint(api_key)
    label = mask_api_key(api_key)
    try:
        user = _http_json(f"{_API_BASE}/user", api_key)
        sub = user.get("subscription") or {}
        if not sub:
            try:
                sub = _http_json(f"{_API_BASE}/user/subscription", api_key)
            except Exception:
                sub = {}

        used = sub.get("character_count")
        limit = sub.get("character_limit")
        remaining = None
        if isinstance(used, int) and isinstance(limit, int):
            remaining = max(0, limit - used)

        reset_unix = sub.get("next_character_count_reset_unix")
        created = user.get("created_at")
        if created is not None:
            try:
                created = int(created)
            except (TypeError, ValueError):
                created = None

        return KeyQuota(
            fingerprint=fp,
            label=label,
            ok=True,
            tier=str(sub.get("tier") or "") or None,
            status=str(sub.get("status") or "") or None,
            character_count=int(used) if used is not None else None,
            character_limit=int(limit) if limit is not None else None,
            remaining=remaining,
            next_reset_unix=int(reset_unix) if reset_unix is not None else None,
            next_reset_iso=_iso_from_unix(reset_unix if reset_unix is not None else None),
            created_at_unix=created,
            created_at_iso=_iso_from_unix(created),
            user_id=str(user.get("user_id") or "") or None,
        )
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:400]
        except Exception:
            pass
        logger.warning("ElevenLabs quota {} HTTP {}: {}", label, exc.code, body[:200])
        # Clef restreinte : TTS marche souvent sans user_read.
        if exc.code in (401, 403) and (
            "user_read" in body or "missing_permissions" in body
        ):
            return KeyQuota(
                fingerprint=fp,
                label=label,
                ok=True,
                quota_readable=False,
                error=(
                    "Permission user_read absente : TTS OK, mais quota/date invisibles. "
                    "Active « User » (Read) sur la clef ElevenLabs."
                ),
            )
        return KeyQuota(
            fingerprint=fp,
            label=label,
            ok=False,
            quota_readable=False,
            error=f"HTTP {exc.code}: {body or exc.reason}",
        )
    except Exception as exc:
        logger.warning("ElevenLabs quota {} erreur: {}", label, exc)
        return KeyQuota(fingerprint=fp, label=label, ok=False, error=str(exc))


def refresh_pool(*, force: bool = False) -> List[KeyQuota]:
    """
    Rafraichit le cache quotas de toutes les clefs.

    @param force Ignore TTL.
    @returns Liste KeyQuota (active marquee).
    """
    with _lock:
        now = time.monotonic()
        if (
            not force
            and _cache["keys"]
            and (now - float(_cache["fetched_at"])) < _CACHE_TTL_SEC
        ):
            return list(_cache["keys"])

        raw_keys = parse_api_keys_from_env()
        quotas: List[KeyQuota] = []
        for k in raw_keys:
            quotas.append(fetch_key_quota(k))

        active_fp = _cache.get("active_fingerprint")
        # Choisit / valide la clef active.
        chosen = _pick_best(quotas, prefer_fp=active_fp)
        for q in quotas:
            q.active = bool(chosen and q.fingerprint == chosen.fingerprint)
        if chosen:
            _cache["active_fingerprint"] = chosen.fingerprint

        _cache["keys"] = quotas
        _cache["fetched_at"] = now
        return list(quotas)


def _pick_best(
    quotas: List[KeyQuota],
    *,
    prefer_fp: Optional[str] = None,
) -> Optional[KeyQuota]:
    """
    Selectionne la meilleure clef (reste > 0, sinon max remaining).

    @param quotas Etats.
    @param prefer_fp Prefere cette empreinte si encore ok.
    @returns KeyQuota ou None.
    """
    usable = [q for q in quotas if q.ok]
    if not usable:
        return None

    known = [
        q
        for q in usable
        if q.quota_readable and q.remaining is not None and q.remaining > 0
    ]
    pool = known if known else usable

    if prefer_fp:
        for q in pool:
            if q.fingerprint == prefer_fp:
                if (not q.quota_readable) or (q.remaining is None) or q.remaining > 0:
                    return q
                break

    pool.sort(
        key=lambda q: (
            1 if q.quota_readable else 0,
            q.remaining if q.remaining is not None else -1,
            q.character_limit if q.character_limit is not None else 0,
        ),
        reverse=True,
    )
    return pool[0]


def resolve_active_api_key(*, force_refresh: bool = False) -> Optional[str]:
    """
    Retourne la clef API a utiliser (auto-switch si quota epuise).

    @param force_refresh Force refresh quotas.
    @returns Clef brute ou None.
    """
    raw_keys = parse_api_keys_from_env()
    if not raw_keys:
        return None

    quotas = refresh_pool(force=force_refresh)
    active_fp = None
    with _lock:
        active_fp = _cache.get("active_fingerprint")

    chosen = _pick_best(quotas, prefer_fp=active_fp)
    if chosen is None:
        return raw_keys[0]

    # Map fingerprint → key
    for k in raw_keys:
        if key_fingerprint(k) == chosen.fingerprint:
            with _lock:
                _cache["active_fingerprint"] = chosen.fingerprint
            return k
    return raw_keys[0]


def set_active_fingerprint(fingerprint: str) -> Optional[KeyQuota]:
    """
    Force une clef active (si encore dans le pool).

    @param fingerprint Empreinte.
    @returns Quota de la clef ou None.
    """
    quotas = refresh_pool(force=True)
    raw_keys = parse_api_keys_from_env()
    fps = {key_fingerprint(k) for k in raw_keys}
    if fingerprint not in fps:
        return None
    with _lock:
        _cache["active_fingerprint"] = fingerprint
        for q in _cache["keys"]:
            q.active = q.fingerprint == fingerprint
    for q in quotas:
        if q.fingerprint == fingerprint:
            q.active = True
            return q
    return None


def pool_status(*, force: bool = False) -> Dict[str, Any]:
    """
    Snapshot public du pool pour l'UI.

    @param force Refresh.
    @returns Dict keys + active.
    """
    quotas = refresh_pool(force=force)
    active = next((q for q in quotas if q.active), None)
    return {
        "count": len(quotas),
        "active_fingerprint": active.fingerprint if active else None,
        "active_label": active.label if active else None,
        "keys": [q.to_public_dict() for q in quotas],
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def mark_key_exhausted(api_key: str) -> Optional[str]:
    """
    Apres un 429, force un switch vers une autre clef.

    @param api_key Clef qui a echoue.
    @returns Nouvelle clef ou None.
    """
    fp = key_fingerprint(api_key)
    quotas = refresh_pool(force=True)
    for q in quotas:
        if q.fingerprint == fp and q.remaining is not None:
            q.remaining = 0
            q.character_count = q.character_limit
    with _lock:
        if _cache.get("active_fingerprint") == fp:
            _cache["active_fingerprint"] = None
    return resolve_active_api_key(force_refresh=False)
