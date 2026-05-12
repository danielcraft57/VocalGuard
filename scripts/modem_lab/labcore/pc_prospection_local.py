#!/usr/bin/env python3
"""
Prospection locale (PC) sans ML : enchaînement d’intents JSON + matching par sous-chaînes.

Aligné sur les packs ``data/intents/danielcraft/outbound/*.json`` et les WAV
``{tag}_NN.wav`` générés dans un dossier pack (ex. ``ui_pack``).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from labaudio.intent_wav_pack import list_intent_variants_on_disk

# Ordre métier : niveau 1 → objections / qualif → offres → closing → relance.
# Les patterns plus spécifiques doivent rester en tête dans chaque fichier ;
# ici on respecte le funnel DanielCraft.
DEFAULT_DANIELCRAFT_OUTBOUND_REL_CHAIN: tuple[str, ...] = (
    "data/intents/danielcraft/outbound/niveau1_ouverture.json",
    "data/intents/danielcraft/outbound/objections.json",
    "data/intents/danielcraft/outbound/niveau2_qualification.json",
    "data/intents/danielcraft/outbound/qualification.json",
    "data/intents/danielcraft/outbound/offres_prix.json",
    "data/intents/danielcraft/outbound/niveau3_negociation_closing.json",
    "data/intents/danielcraft/outbound/niveau4_relance_marketing.json",
)


def resolve_chain_paths(project_root: Path, rel_paths: Sequence[str]) -> list[Path]:
    out: list[Path] = []
    for rel in rel_paths:
        p = (project_root / rel).resolve()
        if p.is_file():
            out.append(p)
    return out


def iter_intent_tag_patterns_from_json(path: Path) -> Iterator[tuple[str, list[str]]]:
    """Pour un fichier : (tag, patterns) dans l’ordre du JSON."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    for item in payload.get("intents") or []:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        if not tag:
            continue
        pats = [str(p or "").strip() for p in (item.get("patterns") or [])]
        pats = [p for p in pats if p]
        if pats:
            yield tag, pats


def merge_intent_chain_rows(paths: Iterable[Path]) -> list[tuple[str, list[str]]]:
    """Fusionne plusieurs JSON en une liste (tag, patterns), ordre fichiers puis intents."""
    rows: list[tuple[str, list[str]]] = []
    for path in paths:
        rows.extend(iter_intent_tag_patterns_from_json(path))
    return rows


def match_intent_tag(transcript: str, rows: Sequence[tuple[str, list[str]]]) -> str | None:
    """
    Premier intent dont un pattern est sous-chaîne de la transcription (minuscules).
    Même logique que ``match_intent_reply_wav`` mais sur une chaîne fusionnée.
    """
    t = (transcript or "").lower().strip()
    if not t:
        return None
    for tag, patterns in rows:
        for pat in patterns:
            p = pat.lower().strip()
            if p and p in t:
                return tag
    return None


def pick_random_variant_wav(pack_dir: Path, tag: str, rng: random.Random) -> Path | None:
    variants = list_intent_variants_on_disk(pack_dir, tag)
    if not variants:
        return None
    _idx, path = rng.choice(variants)
    return path
