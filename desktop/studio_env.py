"""
Chargement des variables d'environnement pour Commercial Studio (exe ou dev).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _exe_dir() -> Path:
    """Dossier de l'exe PyInstaller ou du script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def normalize_voice_api(url: str) -> str:
    """
    Corrige les confusions frequentes (daemon :8090 / autre :8080 vs API :8000).

    @param url Base API FastAPI.
    @returns URL normalisee.
    """
    u = (url or "").strip().rstrip("/")
    if not u:
        return "http://node14.lan:8000/api/v1"
    for wrong in (":8090", ":8080"):
        if wrong in u:
            u = u.replace(wrong, ":8000")
    if not u.endswith("/api/v1"):
        if u.endswith(":8000"):
            u = f"{u}/api/v1"
    return u


def load_studio_env() -> Path | None:
    """
    Lit studio.env a cote de l'exe (ou a la racine repo en dev).

    @returns Chemin du fichier lu, ou None.
    """
    candidates = (
        _exe_dir() / "studio.env",
        Path(__file__).resolve().parent.parent / "studio.env",
    )
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            if key == "VG_VOICE_API":
                val = normalize_voice_api(val)
            if key in ("VG_STT_TOKEN", "STT_INTERNAL_TOKEN") and val == "<STT_INTERNAL_TOKEN>":
                continue
            if key not in os.environ:
                os.environ[key] = val
        return path
    return None


def bootstrap_stt_from_api(voice_api_base: str) -> bool:
    """
    Recupere STT URL + token depuis node14 (deja aligne avec node15).

    @param voice_api_base Ex. http://node14.lan:8000/api/v1
    @returns True si un token a ete recupere.
    """
    if (os.environ.get("VG_STT_TOKEN") or os.environ.get("STT_INTERNAL_TOKEN") or "").strip():
        return False
    import httpx

    base = normalize_voice_api(voice_api_base)
    url = f"{base.rstrip('/')}/kb/outbound-commercial/studio-config"
    try:
        res = httpx.get(url, timeout=8.0)
        if res.status_code >= 400:
            return False
        data = res.json()
        token = str(data.get("stt_token") or "").strip()
        stt_url = str(data.get("stt_url") or "").strip()
        if stt_url:
            os.environ.setdefault("VG_STT_URL", stt_url.rstrip("/"))
        if token and token != "<STT_INTERNAL_TOKEN>":
            os.environ["VG_STT_TOKEN"] = token
            return True
    except Exception:
        return False
    return False


def studio_env_path() -> Path:
    """
    Fichier studio.env prefere (a cote de l'exe ou racine repo).

    @returns Chemin cible lecture/ecriture.
    """
    exe_side = _exe_dir() / "studio.env"
    if exe_side.is_file():
        return exe_side
    root_side = Path(__file__).resolve().parent.parent / "studio.env"
    if root_side.is_file():
        return root_side
    return exe_side


def persist_studio_env(updates: dict[str, str]) -> Path:
    """
    Met a jour studio.env et os.environ (gain micro, volume, etc.).

    @param updates Cle/valeur sans export.
    @returns Chemin ecrit.
    """
    path = studio_env_path()
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    keyed: dict[str, str] = {}
    preserved: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            preserved.append(raw)
            continue
        parse = line
        if parse.lower().startswith("export "):
            parse = parse[7:].strip()
        key, val = parse.split("=", 1)
        keyed[key.strip()] = val.strip()
    keyed.update(updates)
    out_lines = list(preserved)
    for key in sorted(keyed.keys()):
        out_lines.append(f"{key}={keyed[key]}")
    if not any("=" in ln for ln in out_lines):
        out_lines = ["# VocalGuard Commercial Studio"]
        for key in sorted(keyed.keys()):
            out_lines.append(f"{key}={keyed[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    for key, val in updates.items():
        os.environ[key] = val
    return path
