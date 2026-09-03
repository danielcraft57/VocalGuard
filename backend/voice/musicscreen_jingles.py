"""
Catalogue des jingles MusicScreen (libres de droit) pour l'intro messagerie.

Source : https://www.musicscreen.be/musique-libre-de-droit-jingles1.html
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

JINGLES_DIR = Path("resources") / "voice" / "jingles"
CATALOG_FILENAME = "catalog.json"
SOURCE_URL = "https://www.musicscreen.be/musique-libre-de-droit-jingles1.html"


@lru_cache(maxsize=1)
def _load_catalog_raw() -> list[dict[str, Any]]:
    """
    Charge le catalogue JSON embarque dans le depot.

    @returns Liste des entrees jingle.
    """
    candidates = [
        Path.cwd() / JINGLES_DIR / CATALOG_FILENAME,
    ]
    for base in (Path(__file__).resolve().parents[2],):
        candidates.append(base / JINGLES_DIR / CATALOG_FILENAME)
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except (OSError, json.JSONDecodeError):
                continue
    return []


def list_musicscreen_jingles() -> list[dict[str, Any]]:
    """
    Liste les jingles disponibles (id, label, duree).

    @returns Entrees triees par label.
    """
    items = [
        {
            "id": str(entry["id"]),
            "label": str(entry.get("label") or entry["id"]),
            "duration_sec": entry.get("duration_sec"),
            "filename": str(entry.get("filename") or ""),
        }
        for entry in _load_catalog_raw()
        if entry.get("id")
    ]
    return sorted(items, key=lambda row: row["label"].lower())


def get_musicscreen_jingle(jingle_id: str) -> Optional[dict[str, Any]]:
    """
    Retourne une entree catalogue par identifiant.

    @param jingle_id Identifiant stable (ex. tesla).
    @returns Entree ou None.
    """
    needle = (jingle_id or "").strip().lower()
    for entry in _load_catalog_raw():
        if str(entry.get("id", "")).lower() == needle:
            return entry
    return None


def is_musicscreen_jingle(jingle_id: str) -> bool:
    """
    True si l'identifiant correspond a un jingle MusicScreen embarque.

    @param jingle_id Variante configuree.
    @returns Etat catalogue.
    """
    return get_musicscreen_jingle(jingle_id) is not None


def musicscreen_jingle_path(config_base: Path, jingle_id: str) -> Optional[Path]:
    """
    Chemin absolu du MP3 jingle si present sur disque.

    @param config_base Racine projet.
    @param jingle_id Identifiant catalogue.
    @returns Path MP3 ou None.
    """
    entry = get_musicscreen_jingle(jingle_id)
    if not entry:
        return None
    filename = str(entry.get("filename") or "").strip()
    if not filename:
        return None
    path = config_base / JINGLES_DIR / filename
    return path if path.is_file() else None


def resolve_musicscreen_jingle(config_base: Path, jingle_id: str) -> Optional[Path]:
    """
    Resout le jingle actif avec repli sur le premier du catalogue.

    @param config_base Racine projet.
    @param jingle_id Identifiant demande.
    @returns MP3 existant ou None.
    """
    path = musicscreen_jingle_path(config_base, jingle_id)
    if path:
        return path
    catalog = list_musicscreen_jingles()
    if not catalog:
        return None
    return musicscreen_jingle_path(config_base, catalog[0]["id"])


def estimated_musicscreen_intro_end_ms(jingle_id: str, cap_ms: int) -> int:
    """
    Duree effective de l'intro MusicScreen (cap utilisateur + duree fichier).

    @param jingle_id Identifiant jingle.
    @param cap_ms Plafond configure (greeting_intro_sec).
    @returns Duree en millisecondes.
    """
    entry = get_musicscreen_jingle(jingle_id)
    if entry and entry.get("duration_sec"):
        file_ms = int(float(entry["duration_sec"]) * 1000)
        return min(cap_ms, file_ms) if cap_ms > 0 else file_ms
    return cap_ms
