#!/usr/bin/env python3
"""
Tests HTTP « stack » VocalGuard (API + daemon téléphonie + relais interne optionnel).

Usage (depuis la racine du dépôt) :
  python scripts/test_api_stack.py
  python scripts/test_api_stack.py --api-origin http://127.0.0.1:8000 --daemon-url http://node11.lan:8090

Variables d'environnement (priorité après les arguments) :
  VOCALGUARD_API_ORIGIN   ex. http://127.0.0.1:8000  (sans /api/v1 ; /health est à la racine)
  NEXT_PUBLIC_API_BASE_URL  si défini, l'origine est dérivée en retirant /api/v1
  TELEPHONY_DAEMON_URL    pour GET .../health du daemon (optionnel)

Le jeton TELEPHONY_INTERNAL_TOKEN est lu depuis --env-file (.env ou .env.prod par défaut).

Code sortie : 0 OK, 1 échec.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _strip_api_suffix(base: str) -> str:
    b = base.strip().rstrip("/")
    for suf in ("/api/v1", "/api/v1/"):
        if b.endswith(suf):
            return b[: -len(suf)].rstrip("/") or b
    return b


def _default_api_origin() -> str:
    raw = (os.environ.get("VOCALGUARD_API_ORIGIN") or "").strip()
    if raw:
        return _strip_api_suffix(raw).rstrip("/")
    np = (os.environ.get("NEXT_PUBLIC_API_BASE_URL") or "").strip()
    if np:
        return _strip_api_suffix(np).rstrip("/")
    return "http://127.0.0.1:8000"


def _read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        if "=" not in t:
            continue
        k, _, v = t.partition("=")
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        out[key] = val
    return out


def _get_json(url: str, timeout: float = 15.0) -> tuple[int, dict | list | str]:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        code = resp.getcode()
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return code, json.loads(raw)
        except json.JSONDecodeError:
            return code, raw


def _post_json(url: str, headers: dict[str, str], body: dict, timeout: float = 15.0) -> tuple[int, str]:
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    req = Request(url, data=data, headers=h, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main() -> int:
    root = _repo_root()
    ap = argparse.ArgumentParser(description="Smoke HTTP VocalGuard (full stack API checks)")
    ap.add_argument(
        "--api-origin",
        default=None,
        help="Origine API (ex. http://127.0.0.1:8000), sans /api/v1",
    )
    ap.add_argument(
        "--daemon-url",
        default=None,
        help="URL du daemon téléphonie pour GET /health (ex. http://node11.lan:8090)",
    )
    ap.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Fichier .env pour TELEPHONY_INTERNAL_TOKEN / TELEPHONY_DAEMON_URL",
    )
    ap.add_argument(
        "--skip-internal",
        action="store_true",
        help="Ne pas tester POST /api/v1/internal/telephony-events",
    )
    ap.add_argument(
        "--skip-daemon",
        action="store_true",
        help="Ne pas tester GET daemon /health",
    )
    args = ap.parse_args()

    env_path = args.env_file or (root / ".env")
    env_vals = _read_dotenv(env_path)
    if not env_vals and (root / ".env.prod").is_file():
        env_vals = _read_dotenv(root / ".env.prod")

    api_origin = (args.api_origin or _default_api_origin()).rstrip("/")
    daemon_url = (args.daemon_url or os.environ.get("TELEPHONY_DAEMON_URL") or env_vals.get("TELEPHONY_DAEMON_URL") or "").strip().rstrip("/")

    print(f"== API origin: {api_origin}")
    errors = 0

    # 1) GET /health
    health_url = f"{api_origin}/health"
    print(f"== GET {health_url}")
    try:
        code, body = _get_json(health_url)
        print(f"   HTTP {code} {body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)[:500]}")
        if code != 200:
            errors += 1
    except (URLError, TimeoutError, OSError) as e:
        print(f"   ECHEC: {e}")
        errors += 1

    # 2) GET daemon /health
    if not args.skip_daemon and daemon_url:
        dh = f"{daemon_url}/health"
        print(f"== GET {dh}")
        try:
            code, body = _get_json(dh, timeout=8.0)
            print(f"   HTTP {code} {body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)[:500]}")
            if code != 200:
                errors += 1
        except (URLError, TimeoutError, OSError) as e:
            print(f"   ATTENTION (daemon): {e}")
            errors += 1
    elif not args.skip_daemon:
        print("== Daemon: pas d'URL (TELEPHONY_DAEMON_URL / --daemon-url) — skip")

    # 3) POST internal telephony-events
    token = env_vals.get("TELEPHONY_INTERNAL_TOKEN") or os.environ.get("TELEPHONY_INTERNAL_TOKEN") or ""
    internal_url = f"{api_origin}/api/v1/internal/telephony-events"
    if not args.skip_internal:
        if token:
            payload = {
                "event_type": "call.session.log",
                "timestamp": "2026-05-02T12:00:00Z",
                "data": {
                    "call_id": 1,
                    "phone_number": "000",
                    "message": "test_api_stack.py",
                    "level": "info",
                },
                "source": "test_api_stack.py",
            }
            print(f"== POST {internal_url}")
            code, text = _post_json(
                internal_url,
                {"X-VocalGuard-Internal": token},
                payload,
            )
            print(f"   HTTP {code} {text[:400]}")
            if code != 202:
                errors += 1
        else:
            print("== POST interne: TELEPHONY_INTERNAL_TOKEN absent — skip (ajoute-le dans .env)")
    else:
        print("== POST interne: --skip-internal")

    if errors:
        print(f"\nECHEC: {errors} erreur(s).", file=sys.stderr)
        return 1
    print("\nOK test_api_stack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
