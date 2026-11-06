"""
Configuration Prospector (prospector.env + variables d'environnement).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Racine du depot VocalGuard."""
    return Path(__file__).resolve().parents[2]


def exe_dir() -> Path:
    """Dossier exe PyInstaller ou racine repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return repo_root()


def default_db_path() -> Path:
    """
    Fichier SQLite utilisateur par defaut.

    @returns Chemin prospector.db sous Documents.
    """
    docs = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Documents"
    return docs / "VocalGuard" / "prospector" / "prospector.db"


def database_url() -> str:
    """
    URL SQLAlchemy pour la base locale.

    @returns sqlite:///...
    """
    explicit = (os.environ.get("VG_PROSPECTOR_DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    db_path = (os.environ.get("VG_PROSPECTOR_DB") or "").strip()
    if db_path:
        p = Path(db_path)
    else:
        p = default_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p.as_posix()}"


def load_prospector_env() -> Path | None:
    """
    Charge prospector.env a cote de l'exe ou a la racine repo.

    @returns Chemin lu ou None.
    """
    candidates = (
        exe_dir() / "prospector.env",
        repo_root() / "prospector.env",
        repo_root() / "desktop" / "prospector.env",
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
            if key and key not in os.environ:
                os.environ[key] = val
        return path
    return None


def prospectlab_base_url() -> str:
    """Base URL API publique ProspectLab (sans /api/public)."""
    base = (os.environ.get("PROSPECTLAB_URL") or os.environ.get("VG_PROSPECTLAB_URL") or "").strip()
    return base.rstrip("/")


def prospectlab_api_prefix() -> str:
    """Prefixe /api/public."""
    return f"{prospectlab_base_url()}/api/public" if prospectlab_base_url() else ""


def prospectlab_token() -> str:
    """Bearer token ProspectLab."""
    return (os.environ.get("PROSPECTLAB_TOKEN") or os.environ.get("VG_PROSPECTLAB_TOKEN") or "").strip()


def stt_http_url() -> str:
    """URL HTTP STT node15."""
    return (os.environ.get("VG_STT_URL") or "http://node15.lan:8100").strip().rstrip("/")


def stt_ws_url() -> str:
    """
    URL WebSocket transcription.

    @returns ws://.../ws/v1/transcribe
    """
    custom = (os.environ.get("VG_STT_WS") or "").strip()
    if custom:
        return custom
    http = stt_http_url()
    if http.startswith("https://"):
        return http.replace("https://", "wss://", 1) + "/ws/v1/transcribe"
    if http.startswith("http://"):
        return http.replace("http://", "ws://", 1) + "/ws/v1/transcribe"
    return "ws://node15.lan:8100/ws/v1/transcribe"


def stt_token() -> str:
    """Token STT interne."""
    return (os.environ.get("VG_STT_TOKEN") or os.environ.get("STT_INTERNAL_TOKEN") or "").strip()


def modem_com_port() -> str:
    """Port COM modem USB."""
    return (os.environ.get("VG_MODEM_COM") or os.environ.get("MODEM_PORT") or "").strip()


def modem_baudrate() -> int:
    """Baudrate modem."""
    raw = (os.environ.get("VG_MODEM_BAUD") or "230400").strip()
    try:
        return int(raw)
    except ValueError:
        return 230400
