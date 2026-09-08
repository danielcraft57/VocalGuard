"""
Decoupe une transcription en cues type SRT (4 a 5 mots) avec timestamps.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

WORDS_PER_CUE = 5
_WORD_RE = re.compile(r"\S+")


def split_words(text: str) -> list[str]:
    """
    Tokenise un texte en mots (ponctuation conservee).

    @param text Transcription brute.
    @returns Liste de mots non vides.
    """
    trimmed = (text or "").strip()
    if not trimmed:
        return []
    return _WORD_RE.findall(trimmed)


def chunk_words(words: list[str], words_per_cue: int = WORDS_PER_CUE) -> list[list[str]]:
    """
    Groupe les mots par paquets de 4-5 (dernier paquet fusionne s'il n'a qu'un mot).

    @param words Liste de mots.
    @param words_per_cue Taille cible.
    @returns Groupes de mots.
    """
    size = max(4, min(5, int(words_per_cue) or 5))
    if not words:
        return []
    groups: list[list[str]] = [words[i : i + size] for i in range(0, len(words), size)]
    if len(groups) >= 2 and len(groups[-1]) == 1:
        last = groups.pop()
        groups[-1].extend(last)
    return groups


def _timed_groups(
    groups: list[list[str]],
    start: float,
    end: float,
    index_start: int,
) -> list[dict[str, Any]]:
    """Repartit le temps d'une fenetre sur des groupes de mots."""
    if not groups:
        return []
    weights = [sum(max(len(w), 1) for w in g) for g in groups]
    total_w = sum(weights) or 1
    duration = max(float(end) - float(start), 0.05)
    cursor = float(start)
    cues: list[dict[str, Any]] = []
    for i, group in enumerate(groups):
        slice_dur = duration * (weights[i] / total_w)
        g_start = cursor
        g_end = float(end) if i == len(groups) - 1 else cursor + slice_dur
        cursor = g_end
        gw = weights[i] or 1
        w_cursor = g_start
        word_cues: list[dict[str, Any]] = []
        for wi, word in enumerate(group):
            w_slice = (g_end - g_start) * (max(len(word), 1) / gw)
            w_start = w_cursor
            w_end = g_end if wi == len(group) - 1 else w_cursor + w_slice
            w_cursor = w_end
            word_cues.append({"text": word, "start": round(w_start, 3), "end": round(w_end, 3)})
        cues.append(
            {
                "index": index_start + i,
                "start": round(g_start, 3),
                "end": round(g_end, 3),
                "words": word_cues,
            }
        )
    return cues


def _parse_time(value: Any) -> Optional[float]:
    """Convertit un timestamp Whisper en secondes."""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not (num == num) or num < 0:
        return None
    return num


def normalize_whisper_segments(raw: Iterable[Any]) -> list[dict[str, Any]]:
    """
    Normalise les segments whisper-server / faster-whisper.

    @param raw Segments bruts.
    @returns Liste {start, end, text}.
    """
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        start = _parse_time(item.get("start"))
        end = _parse_time(item.get("end"))
        if start is None:
            start = _parse_time(item.get("t0"))
            if start is not None and start > 1000:
                start = start / 100.0
        if end is None:
            end = _parse_time(item.get("t1"))
            if end is not None and end > 1000:
                end = end / 100.0
        if not text or start is None or end is None or end <= start:
            continue
        out.append({"start": start, "end": end, "text": text})
    return out


def build_transcript_cues(
    text: str,
    duration_sec: float = 0.0,
    segments: Optional[list[dict[str, Any]]] = None,
    words_per_cue: int = WORDS_PER_CUE,
) -> list[dict[str, Any]]:
    """
    Construit des cues 4-5 mots. Prefere les timestamps Whisper s'ils existent.

    @param text Transcription complete.
    @param duration_sec Duree audio (secondes).
    @param segments Segments Whisper optionnels.
    @param words_per_cue Taille des groupes.
    @returns Cues serialisables (extra_data / JSON).
    """
    segs = normalize_whisper_segments(segments or [])
    if segs:
        cues: list[dict[str, Any]] = []
        for seg in segs:
            groups = chunk_words(split_words(seg["text"]), words_per_cue)
            cues.extend(_timed_groups(groups, seg["start"], seg["end"], len(cues)))
        for i, cue in enumerate(cues):
            cue["index"] = i
        return cues

    words = split_words(text)
    if not words:
        return []
    groups = chunk_words(words, words_per_cue)
    duration = (
        float(duration_sec)
        if duration_sec and duration_sec > 0.4
        else max(len(groups) * 1.6, 1.0)
    )
    return _timed_groups(groups, 0.0, duration, 0)


def offset_transcript_cues(
    cues: list[dict[str, Any]],
    offset_sec: float,
) -> list[dict[str, Any]]:
    """
    Decale toutes les timestamps de cues (accueil seed en tete du WAV).

    @param cues Cues existants (start/end/words).
    @param offset_sec Secondes a ajouter.
    @returns Nouveaux cues decales (copie).
    """
    delta = float(offset_sec or 0.0)
    if abs(delta) < 0.01 or not cues:
        return list(cues)
    out: list[dict[str, Any]] = []
    for cue in cues:
        words_in = cue.get("words") if isinstance(cue.get("words"), list) else []
        words_out = []
        for w in words_in:
            if not isinstance(w, dict):
                continue
            words_out.append(
                {
                    **w,
                    "start": round(float(w.get("start") or 0.0) + delta, 3),
                    "end": round(float(w.get("end") or 0.0) + delta, 3),
                }
            )
        out.append(
            {
                **cue,
                "start": round(float(cue.get("start") or 0.0) + delta, 3),
                "end": round(float(cue.get("end") or 0.0) + delta, 3),
                "words": words_out,
            }
        )
    return out
