"""
Choix du **premier message audio** (ouverture) dans un pack d’intents.

Complète l’ancienne convention ``greeting_01.wav`` : ici on cible un **tag** JSON
(ex. ``n1_salutation_standard``) et on tire **au hasard** une variante parmi les
fichiers ``{tag}_01.wav``, ``{tag}_02.wav``, … présents sur disque.

**Inférence du tag** depuis les fichiers ``--intents-json`` (ordre = chaîne) :

1. Dans chaque JSON, si une intention a le tag ``greeting`` (sans tenir compte de la casse),
   ce tag est utilisé pour l’ouverture (convention historique du jeu ``lab``).
2. Sinon, **premier intent** avec un ``tag`` non vide dans ce fichier — en général la salutation
   en niveau 1 (ex. ``n1_salutation_standard``).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from labaudio.intent_wav_pack import list_intent_variants_on_disk


def infer_opening_tag_from_intent_json_paths(intent_json_paths: tuple[Path, ...]) -> str | None:
    """
    Déduit le tag WAV d’ouverture à partir des JSON d’intents (priorité au tag nommé « greeting »).

    Parcourt les fichiers dans l’ordre métier ; dans chaque fichier, préfère ``tag == greeting``
    puis sinon le premier intent avec un tag renseigné.
    """
    for path in intent_json_paths:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        intents = data.get("intents") or []
        if not isinstance(intents, list) or not intents:
            continue
        for item in intents:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag") or "").strip()
            if tag.lower() == "greeting":
                return tag
        for item in intents:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag") or "").strip()
            if tag:
                return tag
    return None


def pick_opening_wav_from_pack(
    pack_dir: Path,
    opening_tag: str,
    rng: random.Random,
) -> Path | None:
    """
    Sélectionne un fichier WAV d’ouverture pour ``opening_tag``.

    :param pack_dir: répertoire du pack (même que les réponses intent).
    :param opening_tag: valeur ``tag`` dans le JSON (ex. ``n1_salutation_standard``).
    :param rng: générateur **injecté** (seed contrôlée depuis ``ProspectionDialogueConfig``).
    :returns: chemin vers un ``.wav`` existant, ou ``None`` si aucune variante.
    """
    variants = list_intent_variants_on_disk(pack_dir, opening_tag)
    if not variants:
        return None
    _idx, path = rng.choice(variants)
    return path
