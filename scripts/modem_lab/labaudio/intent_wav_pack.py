#!/usr/bin/env python3
"""
Génération de WAV modem (8 kHz, mono, 8-bit) à partir de fichiers d’intents JSON (dossier ``data/``).

Réutilise la chaîne edge-tts + pydub du dépôt via ``audio_utils.export_wav_8k_8bit``.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple

from loguru import logger

_MODEM_LAB = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _MODEM_LAB.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from audio_utils import apply_wav_riff_info_tags, export_wav_8k_8bit

_RE_VARS = re.compile(r"\{\{\s*(\w+)\s*\}\}")
IntentPackMeta = dict[str, str]


def substitute_intent_placeholders(text: str, mapping: dict[str, str]) -> str:
    """Remplace ``{{cle}}`` par ``mapping['cle']`` (chaîne vide si absente)."""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return mapping.get(key, "")

    return _RE_VARS.sub(repl, text)


def _safe_name(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in value).strip("_")[:80] or "intent"


def _humanize_stem(stem: str) -> str:
    s = stem.replace("_", " ").strip()
    return " ".join(s.split()) or stem


def _riff_title_for_base(base: str) -> str:
    return _humanize_stem(base)


def apply_intent_pack_wav_metadata(
    out_wav: Path,
    *,
    riff_base: str,
    riff_album: str,
    riff_intent_json_stem: str,
    voice: str,
    text: str,
    metadata: IntentPackMeta | None = None,
) -> None:
    """Écrit les tags RIFF LIST/INFO (sans régénérer l’audio)."""
    meta = metadata or {}
    year_value = meta.get("year", "").strip() or str(datetime.now().year)
    comment_bits: list[str] = []
    if riff_intent_json_stem:
        comment_bits.append(f"intents: {riff_intent_json_stem}")
    if text.strip():
        comment_bits.append(text.strip()[:800])
    apply_wav_riff_info_tags(
        out_wav,
        title=_riff_title_for_base(riff_base),
        artist=voice,
        album=riff_album,
        subtitle=meta.get("subtitle", "").strip(),
        year=year_value,
        track_number=meta.get("track_number", "").strip(),
        genre=meta.get("genre", "").strip(),
        media_origin=meta.get("media_origin", "").strip(),
        copyright_text=meta.get("copyright_text", "").strip(),
        parental_control=meta.get("parental_control", "").strip(),
        parental_control_reason=meta.get("parental_control_reason", "").strip(),
        comment=" · ".join(comment_bits) if comment_bits else "",
        software="VocalGuard intent_wav_pack",
    )


def iter_intent_response_jobs(
    intent_file: Path,
    placeholders: dict[str, str],
) -> Iterator[Tuple[str, str]]:
    """Pour chaque réponse d’intent : (nom_base, texte après substitution)."""
    payload = json.loads(intent_file.read_text(encoding="utf-8"))
    intents = payload.get("intents") or []
    for idx, item in enumerate(intents):
        tag = item.get("tag") or f"intent_{idx + 1}"
        responses = item.get("responses") or []
        for ridx, response in enumerate(responses):
            raw = (response or "").strip()
            if not raw:
                continue
            text = substitute_intent_placeholders(raw, placeholders)
            base = f"{_safe_name(tag)}_{ridx + 1:02d}"
            yield base, text


async def render_response_to_wav_edge(
    text: str,
    voice: str,
    out_wav: Path,
    *,
    riff_base: str,
    riff_album: str,
    riff_intent_json_stem: str,
    metadata: IntentPackMeta | None = None,
    max_retries: int = 4,
) -> None:
    import edge_tts
    from pydub import AudioSegment

    attempts = max(1, int(max_retries))
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with tempfile.TemporaryDirectory(prefix="vg_intent_wav_") as tmp:
                tmp_path = Path(tmp)
                mp3 = tmp_path / "tts.mp3"
                comm = edge_tts.Communicate(text, voice)
                await comm.save(str(mp3))
                seg = AudioSegment.from_file(str(mp3))
                export_wav_8k_8bit(seg, out_wav)
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt >= attempts:
                break
            wait_s = min(8.0, 0.8 * (2 ** (attempt - 1)))
            logger.warning(
                "TTS edge échoué pour {} (tentative {}/{}): {} — retry dans {:.1f}s",
                out_wav.name,
                attempt,
                attempts,
                e,
                wait_s,
            )
            await asyncio.sleep(wait_s)

    if last_err is not None:
        raise RuntimeError(f"edge_tts indisponible pour {out_wav.name} après {attempts} tentatives") from last_err

    apply_intent_pack_wav_metadata(
        out_wav,
        riff_base=riff_base,
        riff_album=riff_album,
        riff_intent_json_stem=riff_intent_json_stem,
        voice=voice,
        text=text,
        metadata=metadata,
    )


async def build_pack_from_json(
    intent_json: Path,
    out_dir: Path,
    placeholders: dict[str, str],
    *,
    voice: str = "fr-FR-DeniseNeural",
    force: bool = False,
    album: str | None = None,
    metadata: IntentPackMeta | None = None,
) -> list[Path]:
    """
    Génère un fichier ``.wav`` par réponse dans ``out_dir``.

    :returns: liste des WAV créés ou ignorés (existants sans ``force``).
    :param album: libellé « album » (chunk IPRD) ; défaut = nom du dossier de sortie.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    album_label = (album or "").strip() or out_dir.name
    intent_stem = intent_json.stem
    written: list[Path] = []
    failed: list[str] = []
    for base, text in iter_intent_response_jobs(intent_json, placeholders):
        target = out_dir / f"{base}.wav"
        if target.exists() and not force:
            logger.info("Existant, skip TTS — mise à jour métadonnées: {}", target.name)
            apply_intent_pack_wav_metadata(
                target,
                riff_base=base,
                riff_album=album_label,
                riff_intent_json_stem=intent_stem,
                voice=voice,
                text=text,
                metadata=metadata,
            )
            written.append(target)
            continue
        logger.info("TTS -> {} ({})", target.name, text[:72] + ("…" if len(text) > 72 else ""))
        try:
            await render_response_to_wav_edge(
                text,
                voice,
                target,
                riff_base=base,
                riff_album=album_label,
                riff_intent_json_stem=intent_stem,
                metadata=metadata,
            )
            written.append(target)
        except Exception as e:
            failed.append(target.name)
            logger.error("TTS KO pour {}: {}", target.name, e)
            continue
    if failed:
        logger.warning("Pack intents partiel: {} fichier(s) en échec TTS: {}", len(failed), ", ".join(failed))
    return written


def parse_placeholder_args(pairs: Iterable[str]) -> dict[str, str]:
    """Parse ``KEY=VAL`` (répétitif)."""
    out: dict[str, str] = {}
    for raw in pairs:
        if "=" not in raw:
            continue
        k, _, v = raw.partition("=")
        k, v = k.strip(), v.strip()
        if k:
            out[k] = v
    return out


def load_placeholders_json(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if k is not None}


def collect_placeholder_keys_from_intent_json(intent_file: Path) -> list[str]:
    """
    Liste les clés ``{{cle}}`` présentes dans les ``responses`` du JSON d’intents.
    """
    if not intent_file.is_file():
        return []
    payload = json.loads(intent_file.read_text(encoding="utf-8"))
    found: set[str] = set()
    for item in payload.get("intents") or []:
        for r in item.get("responses") or []:
            for m in _RE_VARS.finditer(r or ""):
                found.add(m.group(1))
    return sorted(found)


def match_intent_reply_wav(
    transcript: str,
    intents_json: Path,
    pack_dir: Path,
    *,
    response_index: int = 1,
) -> Optional[Path]:
    """
    Choix naïf : première intention dont un ``pattern`` est sous-chaîne de la transcription.
    Fichier attendu : ``{tag}_{response_index:02d}.wav`` dans ``pack_dir``.
    """
    t = transcript.lower().strip()
    if not t or not intents_json.is_file():
        return None
    payload = json.loads(intents_json.read_text(encoding="utf-8"))
    for item in payload.get("intents") or []:
        tag = item.get("tag") or ""
        for pat in item.get("patterns") or []:
            p = (pat or "").lower().strip()
            if p and p in t:
                fname = f"{_safe_name(tag)}_{max(1, int(response_index)):02d}.wav"
                cand = pack_dir / fname
                if cand.is_file():
                    return cand
    return None
