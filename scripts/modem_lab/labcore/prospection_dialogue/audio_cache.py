"""
Préchargement **intents + WAV** pour la prospection sortante.

Charge en mémoire les JSON d’intents (pour validation) et tous les fichiers ``.wav`` du pack
référencés par ces JSON (variantes par tag), ainsi que le **greeting**. Les lectures disque
pour ``half_duplex`` / VTX se font alors sur des **buffers** déjà en RAM, comme le modèle Vosk
préchargé via ``preload_vosk_model``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from labaudio.intent_wav_pack import list_intent_variants_on_disk
from labcore.voice_line import wav_file_to_mono_u8_pcm


def _load_intent_payloads(
    intent_json_paths: tuple[Path, ...],
) -> list[tuple[Path, dict[str, Any]]]:
    out: list[tuple[Path, dict[str, Any]]] = []
    for p in intent_json_paths:
        if not p.is_file():
            raise FileNotFoundError(f"Fichier intents introuvable: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"JSON intents invalide (racine dict attendu): {p}")
        out.append((p, data))
    return out


def _collect_wav_paths_for_intents(pack_dir: Path, payloads: list[tuple[Path, dict[str, Any]]]) -> list[Path]:
    if not pack_dir.is_dir():
        return []
    seen: set[str] = set()
    ordered: list[Path] = []
    for _src, data in payloads:
        for item in data.get("intents") or []:
            tag = str(item.get("tag") or "").strip()
            if not tag:
                continue
            for _idx, wpath in list_intent_variants_on_disk(pack_dir, tag):
                key = str(wpath.resolve())
                if key not in seen:
                    seen.add(key)
                    ordered.append(wpath)
    return ordered


@dataclass
class ProspectionAudioCache:
    """
    PCM mono 8-bit (u8) indexé par chemin **résolu** (``Path.resolve()`` en str).
    """

    u8_by_resolved: dict[str, bytes] = field(default_factory=dict)
    intent_payloads: list[tuple[Path, dict[str, Any]]] = field(default_factory=list)

    def pcm_u8_for_path(self, wav_path: Path) -> bytes | None:
        key = str(Path(wav_path).resolve())
        return self.u8_by_resolved.get(key)


def build_prospection_audio_cache(
    *,
    pack_dir: Path,
    greeting_wav: Path,
    intent_json_paths: tuple[Path, ...],
) -> ProspectionAudioCache:
    """
    Charge tous les WAV utiles : greeting + chaque variante listée pour les tags des JSON.

    :raises FileNotFoundError: JSON ou WAV manquant.
    """
    payloads = _load_intent_payloads(intent_json_paths) if intent_json_paths else []
    paths: list[Path] = []
    g = Path(greeting_wav)
    if g.is_file():
        paths.append(g)
    paths.extend(_collect_wav_paths_for_intents(pack_dir, payloads))

    u8_by_resolved: dict[str, bytes] = {}
    total_bytes = 0
    for p in paths:
        key = str(p.resolve())
        if key in u8_by_resolved:
            continue
        if not p.is_file():
            raise FileNotFoundError(f"WAV prospection introuvable: {p}")
        raw = wav_file_to_mono_u8_pcm(p)
        if not raw:
            logger.warning("PCM vide après lecture: {}", p)
            continue
        u8_by_resolved[key] = raw
        total_bytes += len(raw)

    logger.info(
        "Préchargement audio prospection: {} fichier(s), {} octets PCM u8",
        len(u8_by_resolved),
        total_bytes,
    )
    return ProspectionAudioCache(u8_by_resolved=u8_by_resolved, intent_payloads=payloads)

