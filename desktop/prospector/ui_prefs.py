"""
Preferences UI Prospector (volume, theme) — fichier JSON utilisateur.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from desktop.prospector.settings import default_db_path


def prefs_path() -> Path:
    """Chemin ui_prefs.json."""
    return default_db_path().parent / "ui_prefs.json"


def load_prefs() -> dict[str, Any]:
    """
    Charge les preferences UI.

    @returns Dict (cles absentes si fichier manquant).
    """
    path = prefs_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_prefs(**updates: Any) -> None:
    """
    Fusionne et enregistre les preferences.

    @param updates Cles a mettre a jour.
    """
    data = load_prefs()
    data.update(updates)
    path = prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
