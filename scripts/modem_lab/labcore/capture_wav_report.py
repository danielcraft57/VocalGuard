#!/usr/bin/env python3
"""
Rapport automatique sur une capture ligne (WAV 8 kHz, 8-bit mono unsigned).

Détecte de façon heuristique :
- ``t_first_ring`` : début de la première salve « tonalité / sonnerie » ;
- ``t_last_ring_before_voice`` : fin de la dernière salve sonnerie avant une zone « parole probable » ;
- ``t_speech_candidate`` : début de la première fenêtre « parole probable » (ex. « oui allo » court).

Les fenêtres glissantes (50–100 ms recommandé) permettent de mieux localiser les syllabes courtes
que des blocs 250 ms.
"""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FrameFeat:
    t0: float
    t1: float
    t_center: float
    activity: float
    zcr: float
    periodicity: float
    is_ring: bool
    is_speech: bool


def _activity_score_u8(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    mad = sum(abs(b - 128) for b in chunk) / float(len(chunk))
    span = float(max(chunk) - min(chunk))
    return (0.7 * mad) + (0.3 * span / 2.0)


def _zcr_u8(chunk: bytes) -> float:
    if not chunk or len(chunk) < 2:
        return 0.0
    prev = int(chunk[0]) - 128
    crossings = 0
    for b in chunk[1:]:
        cur = int(b) - 128
        if (prev >= 0 > cur) or (prev < 0 <= cur):
            crossings += 1
        prev = cur
    return crossings / float(len(chunk) - 1)


def _periodicity_u8(chunk: bytes, min_lag: int = 8, max_lag: int = 80) -> float:
    n = len(chunk)
    if n < (max_lag + 2):
        return 0.0
    x = [int(b) - 128 for b in chunk]
    energy = sum(v * v for v in x)
    if energy <= 0:
        return 0.0
    lo = max(1, min_lag)
    hi = min(max_lag, n // 2)
    if lo > hi:
        return 0.0
    best = 0.0
    for lag in range(lo, hi + 1):
        num = sum(x[i] * x[i - lag] for i in range(lag, n))
        score = abs(num) / float(energy)
        if score > best:
            best = score
    return best


def analyze_answer_wav(
    wav_path: Path,
    *,
    frame_ms: float = 80.0,
    hop_ms: float = 40.0,
    ring_activity_min: float = 12.0,
    ring_periodicity_min: float = 0.80,
    speech_activity_min: float = 6.0,
    speech_periodicity_max: float = 0.72,
    speech_zcr_min: float = 0.04,
    speech_zcr_max: float = 0.38,
    min_hops_ring: int = 2,
    min_hops_speech: int = 2,
) -> dict[str, Any]:
    """
    Analyse un WAV et retourne un dict prêt pour JSON + champs dérivés.

    Seuils par défaut calibrés grossièrement sur sonnerie française / parole étroite bande.
    """
    path = Path(wav_path)
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        nframes = w.getnframes()
        pcm = w.readframes(nframes)

    if nch != 1 or sw != 1 or rate != 8000:
        return {
            "analysis_version": 2,
            "error": "WAV attendu: 8000 Hz, mono, 8-bit unsigned",
            "wav_path": str(path),
            "channels": nch,
            "sampwidth": sw,
            "rate": rate,
        }

    frame_n = max(1, int(rate * (frame_ms / 1000.0)))
    hop_n = max(1, int(rate * (hop_ms / 1000.0)))
    duration = nframes / float(rate)

    feats: list[FrameFeat] = []
    i = 0
    while i + frame_n <= len(pcm):
        chunk = pcm[i : i + frame_n]
        act = _activity_score_u8(chunk)
        zcr = _zcr_u8(chunk)
        per = _periodicity_u8(chunk)
        is_ring = act >= ring_activity_min and per >= ring_periodicity_min
        is_speech = (
            act >= speech_activity_min
            and per <= speech_periodicity_max
            and speech_zcr_min <= zcr <= speech_zcr_max
        )
        t0 = i / float(rate)
        t1 = (i + frame_n) / float(rate)
        feats.append(FrameFeat(t0, t1, (t0 + t1) / 2.0, act, zcr, per, is_ring, is_speech))
        i += hop_n

    def _first_sustained(*, ring: bool, min_run: int) -> int | None:
        run = 0
        for idx, f in enumerate(feats):
            ok = f.is_ring if ring else f.is_speech
            if ok:
                run += 1
                if run >= min_run:
                    return idx - min_run + 1
            else:
                run = 0
        return None

    def _merge_intervals(mask: list[bool]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        j = 0
        while j < len(mask):
            if not mask[j]:
                j += 1
                continue
            k = j
            while k < len(mask) and mask[k]:
                k += 1
            out.append((feats[j].t0, feats[k - 1].t1))
            j = k
        return out

    ring_mask = [f.is_ring for f in feats]
    speech_mask = [f.is_speech for f in feats]
    ring_iv = _merge_intervals(ring_mask)
    speech_iv = _merge_intervals(speech_mask)

    ir = _first_sustained(ring=True, min_run=min_hops_ring)
    t_first_ring = feats[ir].t0 if ir is not None else None

    is_speech_first = _first_sustained(ring=False, min_run=min_hops_speech)
    t_speech_candidate: float | None = None
    t_last_ring_before_voice: float | None = None

    if is_speech_first is not None:
        t_speech_candidate = feats[is_speech_first].t0
        # dernière fin de segment « ring » strictement avant le début parole candidate
        cut = t_speech_candidate
        ends_before = [e for s, e in ring_iv if e <= cut + 1e-6]
        if ends_before:
            t_last_ring_before_voice = max(ends_before)
        elif t_first_ring is not None and ring_iv:
            # parole très tôt après ring : prendre la fin du dernier ring avant cut
            cand = [e for s, e in ring_iv if s < cut]
            if cand:
                t_last_ring_before_voice = max(cand)
    else:
        t_last_ring_before_voice = ring_iv[-1][1] if ring_iv else None

    sp_acts = [f.activity for f in feats if f.is_speech]
    ring_acts = [f.activity for f in feats if f.is_ring]
    all_acts = [f.activity for f in feats]
    delta_first: float | None = None
    delta_last: float | None = None
    if t_first_ring is not None and t_speech_candidate is not None:
        delta_first = round(t_speech_candidate - t_first_ring, 3)
    if t_last_ring_before_voice is not None and t_speech_candidate is not None:
        delta_last = round(t_speech_candidate - t_last_ring_before_voice, 3)
    ring_covered = sum(e - s for s, e in ring_iv) if ring_iv else 0.0
    speech_covered = sum(e - s for s, e in speech_iv) if speech_iv else 0.0

    return {
        "analysis_version": 2,
        "wav_path": str(path.resolve()),
        "duration_sec": round(duration, 3),
        "sample_rate_hz": rate,
        "frame_ms": frame_ms,
        "hop_ms": hop_ms,
        "frame_samples": frame_n,
        "hop_samples": hop_n,
        "num_frames": len(feats),
        "t_first_ring": None if t_first_ring is None else round(t_first_ring, 3),
        "t_last_ring_before_voice": None
        if t_last_ring_before_voice is None
        else round(t_last_ring_before_voice, 3),
        "t_speech_candidate": None
        if t_speech_candidate is None
        else round(t_speech_candidate, 3),
        "delta_first_ring_to_speech_sec": delta_first,
        "delta_last_ring_to_speech_sec": delta_last,
        "ring_segment_count": len(ring_iv),
        "speech_segment_count": len(speech_iv),
        "ring_covered_sec": round(ring_covered, 3),
        "speech_covered_sec": round(speech_covered, 3),
        "first_ring_segment": (
            [round(ring_iv[0][0], 3), round(ring_iv[0][1], 3)] if ring_iv else None
        ),
        "first_speech_segment": (
            [round(speech_iv[0][0], 3), round(speech_iv[0][1], 3)] if speech_iv else None
        ),
        "peak_activity_any": round(max(all_acts), 3) if all_acts else None,
        "speech_peak_activity": round(max(sp_acts), 3) if sp_acts else None,
        "speech_mean_activity": round(sum(sp_acts) / len(sp_acts), 3) if sp_acts else None,
        "ring_peak_activity": round(max(ring_acts), 3) if ring_acts else None,
        "ring_segments": [[round(s, 3), round(e, 3)] for s, e in ring_iv],
        "speech_segments": [[round(s, 3), round(e, 3)] for s, e in speech_iv],
        "thresholds": {
            "ring_activity_min": ring_activity_min,
            "ring_periodicity_min": ring_periodicity_min,
            "speech_activity_min": speech_activity_min,
            "speech_periodicity_max": speech_periodicity_max,
            "speech_zcr_min": speech_zcr_min,
            "speech_zcr_max": speech_zcr_max,
            "min_hops_ring": min_hops_ring,
            "min_hops_speech": min_hops_speech,
        },
    }


def write_answer_timing_report(
    wav_path: Path,
    json_path: Path,
    txt_path: Path,
    *,
    session: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Écrit ``report.json`` + ``report.txt`` ; retourne le dict d'analyse.

    ``session`` est fusionné sous la clé ``session`` dans le JSON (résultat attente, fenêtres VRX, etc.).
    """
    data = analyze_answer_wav(wav_path, **kwargs)
    if session:
        data["session"] = dict(session)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"Fichier: {data.get('wav_path', wav_path)}",
        f"Duree: {data.get('duration_sec', '?')} s",
        f"Echantillonnage: {data.get('sample_rate_hz', '?')} Hz",
        f"Fenetre: {data.get('frame_ms', '?')} ms, pas: {data.get('hop_ms', '?')} ms",
        f"Trames analysees: {data.get('num_frames', '?')}",
        "",
        f"t_first_ring:              {data.get('t_first_ring')}",
        f"t_last_ring_before_voice:  {data.get('t_last_ring_before_voice')}",
        f"t_speech_candidate:        {data.get('t_speech_candidate')}",
        f"Delta 1ere sonnerie -> parole: {data.get('delta_first_ring_to_speech_sec')}",
        f"Delta fin sonnerie -> parole: {data.get('delta_last_ring_to_speech_sec')}",
        "",
        f"Segments sonnerie: {data.get('ring_segment_count')} (total ~{data.get('ring_covered_sec')} s)",
        f"Segments parole:   {data.get('speech_segment_count')} (total ~{data.get('speech_covered_sec')} s)",
        f"Pic activite (parole): {data.get('speech_peak_activity')} | (global) {data.get('peak_activity_any')}",
        "",
    ]
    if data.get("session"):
        lines.append("--- Session attente (VRX) ---")
        for k, v in sorted(data["session"].items(), key=lambda x: x[0]):
            lines.append(f"{k}: {v}")
        lines.append("")
    if data.get("error"):
        lines.append(f"ERREUR: {data['error']}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return data
