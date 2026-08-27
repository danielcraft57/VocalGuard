"""
Mode de prise en charge des appels entrants (répondeur vs téléphone parallèle).

- voicemail : modem décroche tout de suite (rings=0) pour couper la sonnerie du fixe
- phone : pas d'ATA, le téléphone parallèle répond seul (journalisation CID)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from loguru import logger

from backend.core.config import Config

IncomingLineMode = Literal["voicemail", "phone"]


def runtime_incoming_mode_path(config: Config) -> Path:
    """
    Chemin du fichier runtime (survit aux redémarrages, sans écraser config.yaml).

    @param config Configuration applicative.
    @returns Chemin absolu du YAML runtime.
    """
    base = Path(config.base_path) if config.base_path else Path.cwd()
    return (base / "data" / "incoming_line_mode.yaml").resolve()


def resolve_incoming_line_mode(config: Config) -> IncomingLineMode:
    """
    Déduit le mode UI depuis la config live.

    @param config Configuration.
    @returns ``voicemail`` ou ``phone``.
    """
    if not bool(getattr(config, "incoming_auto_answer", True)):
        return "phone"
    return "voicemail"


def apply_incoming_line_mode(config: Config, mode: IncomingLineMode) -> IncomingLineMode:
    """
    Applique le mode sur l'objet Config en mémoire.

    @param config Configuration à muter.
    @param mode Mode cible.
    @returns Mode effectivement appliqué.
    """
    if mode == "phone":
        config.incoming_auto_answer = False
        # Laisser sonner le fixe parallele : pas de seize immediat (rings>0 desactive instant_ring_seize).
        rings = int(getattr(config, "phone_mode_rings", 4) or 4)
        config.rings_before_answer = max(2, rings)
    else:
        config.incoming_auto_answer = True
        # rings=0 + saisie voix rapide = coupe la sonnerie du fixe parallèle.
        config.rings_before_answer = 0
    return resolve_incoming_line_mode(config)


def save_incoming_line_mode(config: Config) -> None:
    """
    Persiste le mode courant dans ``data/incoming_line_mode.yaml``.

    @param config Configuration source.
    """
    path = runtime_incoming_mode_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": resolve_incoming_line_mode(config),
        "incoming_auto_answer": bool(config.incoming_auto_answer),
        "rings_before_answer": int(config.rings_before_answer),
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, default_flow_style=False)
    logger.info("Mode entrant sauvegarde: {} ({})", payload["mode"], path)


def load_incoming_line_mode(config: Config) -> Optional[IncomingLineMode]:
    """
    Recharge le mode runtime s'il existe (au démarrage du process).

    @param config Configuration à enrichir.
    @returns Mode chargé, ou None si fichier absent.
    """
    path = runtime_incoming_mode_path(config)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        mode_raw = str(data.get("mode") or "").strip().lower()
        if mode_raw in ("voicemail", "phone"):
            apply_incoming_line_mode(config, mode_raw)  # type: ignore[arg-type]
            logger.info("Mode entrant restaure depuis {}: {}", path, mode_raw)
            return mode_raw  # type: ignore[return-value]
        if "incoming_auto_answer" in data:
            config.incoming_auto_answer = bool(data.get("incoming_auto_answer"))
        if "rings_before_answer" in data:
            try:
                config.rings_before_answer = int(data.get("rings_before_answer"))
            except (TypeError, ValueError):
                pass
        return resolve_incoming_line_mode(config)
    except Exception as exc:
        logger.warning("Lecture mode entrant {}: {}", path, exc)
        return None
