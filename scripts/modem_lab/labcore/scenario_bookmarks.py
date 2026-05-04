"""
Signets (raccourcis) utilisateur : scénario ``cli.py`` + arguments figés.

Fichier : ``<modem_lab>/scenario_bookmarks.json`` (souvent ignoré par git).
Schéma : voir ``scenario_bookmarks.example.json`` à la racine du lab.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

BOOKMARKS_FILENAME = "scenario_bookmarks.json"
_SCHEMA_VERSION = 1

_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def bookmarks_file(lab_dir: Path) -> Path:
    return Path(lab_dir) / BOOKMARKS_FILENAME


def validate_bookmark_id(bookmark_id: str, builtin_scenarios: set[str]) -> str | None:
    """
    Retourne un message d'erreur si invalide, sinon None.
    Les ids ne doivent pas entrer en collision avec les noms de scénarios intégrés.
    """
    bid = bookmark_id.strip()
    if not bid:
        return "identifiant vide"
    if not _ID_RE.match(bid):
        return (
            "identifiant invalide : utiliser lettre en tête puis lettres, chiffres, "
            "tirets ou underscores (max 64 car.)"
        )
    if bid in builtin_scenarios:
        return f"l'identifiant « {bid} » est réservé (scénario intégré)"
    return None


def load_bookmarks(lab_dir: Path) -> dict[str, dict[str, Any]]:
    """Charge les signets ; retourne toujours une copie modifiable des entrées."""
    path = bookmarks_file(lab_dir)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    marks = raw.get("bookmarks")
    if not isinstance(marks, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in marks.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        scen = v.get("scenario")
        if not isinstance(scen, str):
            continue
        args = v.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list):
            continue
        if not all(isinstance(x, str) for x in args):
            continue
        desc = v.get("description", "")
        if desc is not None and not isinstance(desc, str):
            desc = ""
        out[k] = {"scenario": scen, "args": list(args), "description": desc or ""}
    return out


def save_bookmarks(lab_dir: Path, bookmarks: Mapping[str, Mapping[str, Any]]) -> None:
    path = bookmarks_file(lab_dir)
    payload = {
        "version": _SCHEMA_VERSION,
        "bookmarks": {k: dict(v) for k, v in sorted(bookmarks.items())},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def strip_leading_ddashes(argv: list[str]) -> list[str]:
    if argv and argv[0] == "--":
        return list(argv[1:])
    return list(argv)


def merge_bookmark_and_user_args(stored: list[str], user: list[str]) -> list[str]:
    """Arguments signet puis arguments ligne de commande (souvent le dernier gagne côté argparse cible)."""
    return list(stored) + strip_leading_ddashes(user)


def resolve_run(
    target: str,
    *,
    scenario_map: Mapping[str, Path],
    bookmarks: Mapping[str, Mapping[str, Any]],
) -> tuple[Path, list[str]] | None:
    """
    Résout un lancement : soit scénario intégré, soit signet.

    Retourne (script_path, argv_suffix) ou None si inconnu.
    """
    if target in scenario_map:
        return scenario_map[target], []
    entry = bookmarks.get(target)
    if not entry:
        return None
    scen = entry.get("scenario")
    if not isinstance(scen, str) or scen not in scenario_map:
        return None
    args = entry.get("args") or []
    if not isinstance(args, list):
        return None
    return scenario_map[scen], [str(x) for x in args]
