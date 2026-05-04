#!/usr/bin/env python3
"""
Phase partagée après composition : attente décroché/voix, métriques CSV, WAV inline/thread,
rapport timing — même logique que ``answer_metrics_probe``.

Les scénarios ``answer_metrics_probe`` et ``prompt_and_play`` doivent s’appuyer sur ce module
pour garder un seul chemin (VRX, hooks métriques, fenêtre de capture).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from labcore.capture_wav_report import write_answer_timing_report
from labcore.call_watch import wait_answer_or_voice_activity
from labcore.voice_metrics import METRICS_HEADERS, MetricsCsvThreadWriter, write_metrics_csv
from labcore.vrx_wav_recorder_thread import VrxWavRecorderThread


class AnswerWaitConfigError(ValueError):
    """Combinaison d’options capture / enregistrement incompatible."""


async def run_answer_wait_phase(
    modem: Any,
    *,
    eff_wait: float,
    post_answer_observe_sec: float,
    capture_delay_sec: float,
    capture_window_sec: float,
    allow_voice_activity: bool,
    allow_energy_fallback: bool,
    min_voice_trigger_sec: float,
    energy_score_min: float,
    energy_jitter_min: float,
    energy_score_span_min: float,
    energy_jitter_span_min: float,
    tone_reject_enabled: bool,
    tone_reject_zcr_min: float,
    tone_reject_zcr_max: float,
    tone_reject_periodicity_max: float,
    vad_threshold: float,
    vad_min_speech_ms: float,
    vad_hangover_ms: float,
    already_in_voice_mode: bool,
    record_wav_from_start: bool,
    record_wav_mode: str,
    record_wav_out: Path | None,
    record_wav_sec: float,
    metrics_out: Path | None,
    metrics_thread: bool,
    metrics_flush_sec: float,
    auto_report: bool,
    report_frame_ms: float,
    report_hop_ms: float,
    exit_wait_on_voice: bool = False,
    report_session_extra: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    Attend un décroché ou une activité voix avec les mêmes options que la sonde métriques.

    Écrit ``metrics_out`` si fourni ; enregistre le WAV si ``record_wav_from_start`` ;
    génère le rapport si ``auto_report`` et qu’un WAV valide existe.
    """
    cap_delay = max(0.0, float(capture_delay_sec))
    cap_win = max(0.0, float(capture_window_sec))
    if cap_win > 0.0 and record_wav_mode == "thread":
        raise AnswerWaitConfigError(
            "--capture-window-sec > 0 nécessite record_wav_mode inline (conflit VRX / délai)."
        )

    metrics_rows: list[dict[str, Any]] = []
    writer: MetricsCsvThreadWriter | None = None
    rec_thread: VrxWavRecorderThread | None = None

    capture_wav: Path | None = None
    if bool(record_wav_from_start):
        if record_wav_mode == "thread":
            if record_wav_out is None:
                raise AnswerWaitConfigError("record_wav_out requis pour record_wav_mode thread.")
            rec_duration = float(record_wav_sec)
            if rec_duration <= 0.0:
                rec_duration = float(eff_wait) + float(post_answer_observe_sec) + 3.0
            rec_thread = VrxWavRecorderThread(
                asyncio.get_running_loop(),
                modem,
                rec_duration,
                Path(record_wav_out),
                prefer_already_in_voice=False,
                stop_on_remote_hangup=False,
                use_fallback=True,
            )
            rec_thread.start()
            logger.info(
                "Enregistrement WAV (thread) lancé: {} ({:.1f}s)",
                record_wav_out,
                rec_duration,
            )
        else:
            if record_wav_out is None:
                raise AnswerWaitConfigError("record_wav_out requis pour enregistrement inline.")
            capture_wav = Path(record_wav_out)
            logger.info("Enregistrement WAV (inline, même VRX): {}", capture_wav)

    if metrics_out is not None:
        if bool(metrics_thread):
            writer = MetricsCsvThreadWriter(
                metrics_out,
                headers=METRICS_HEADERS,
                flush_interval_sec=float(metrics_flush_sec),
            )
            writer.start()

            def on_metric(row: dict[str, Any]) -> None:
                assert writer is not None
                writer.push(row)
        else:

            def on_metric(row: dict[str, Any]) -> None:
                metrics_rows.append(row)

        metrics_hook = on_metric
    else:
        metrics_hook = None

    try:
        ready, why = await wait_answer_or_voice_activity(
            modem,
            timeout_sec=float(eff_wait),
            already_in_voice_mode=bool(already_in_voice_mode),
            allow_voice_activity=bool(allow_voice_activity),
            allow_energy_fallback=bool(allow_energy_fallback),
            min_voice_trigger_sec=float(min_voice_trigger_sec),
            energy_score_min=float(energy_score_min),
            energy_jitter_min=float(energy_jitter_min),
            energy_score_span_min=float(energy_score_span_min),
            energy_jitter_span_min=float(energy_jitter_span_min),
            tone_reject_enabled=bool(tone_reject_enabled),
            tone_reject_zcr_min=float(tone_reject_zcr_min),
            tone_reject_zcr_max=float(tone_reject_zcr_max),
            tone_reject_periodicity_max=float(tone_reject_periodicity_max),
            post_answer_observe_sec=float(post_answer_observe_sec),
            capture_delay_sec=cap_delay,
            capture_window_sec=cap_win,
            capture_wav_path=capture_wav,
            metrics_hook=metrics_hook,
            vad_threshold=float(vad_threshold),
            vad_min_speech_ms=float(vad_min_speech_ms),
            vad_hangover_ms=float(vad_hangover_ms),
            exit_wait_on_voice=bool(exit_wait_on_voice),
        )
    finally:
        if writer is not None:
            writer.close()
        elif metrics_out is not None and metrics_rows:
            write_metrics_csv(metrics_out, metrics_rows)
        if rec_thread is not None:
            rec_ok = rec_thread.join_result(timeout=5.0)
            logger.info("WAV enregistré: {} (ok={})", record_wav_out, rec_ok)

    if bool(record_wav_from_start) and record_wav_mode == "inline" and record_wav_out is not None:
        p = Path(record_wav_out)
        if p.is_file():
            logger.info("WAV inline: {} ({} octets)", p, p.stat().st_size)
        else:
            logger.warning("WAV inline manquant: {}", p)

    if (
        bool(auto_report)
        and bool(record_wav_from_start)
        and record_wav_out is not None
    ):
        wav_p = Path(record_wav_out)
        if wav_p.is_file() and wav_p.stat().st_size > 64:
            report_json = wav_p.parent / "report.json"
            report_txt = wav_p.parent / "report.txt"
            try:
                sess: dict[str, Any] = {
                    "answer_wait_ready": ready,
                    "answer_wait_reason": why,
                    "capture_delay_sec": cap_delay,
                    "capture_window_sec": cap_win,
                    "eff_wait_sec": float(eff_wait),
                    "post_answer_observe_sec": float(post_answer_observe_sec),
                    "exit_wait_on_voice": bool(exit_wait_on_voice),
                }
                if report_session_extra:
                    sess.update(report_session_extra)
                summary = write_answer_timing_report(
                    wav_p,
                    report_json,
                    report_txt,
                    session=sess,
                    frame_ms=float(report_frame_ms),
                    hop_ms=float(report_hop_ms),
                )
                logger.info(
                    "Rapport timing: t_first_ring={} t_last_ring_before_voice={} t_speech_candidate={} -> {}",
                    summary.get("t_first_ring"),
                    summary.get("t_last_ring_before_voice"),
                    summary.get("t_speech_candidate"),
                    report_json,
                )
            except Exception as e:
                logger.warning("Rapport timing non généré: {}", e)

    if metrics_out is not None:
        logger.info("Métriques écrites: {}", metrics_out)

    return ready, why


def effective_vrx_timeout(
    wait_answer_or_voice_sec: float,
    capture_delay_sec: float,
    capture_window_sec: float,
    *,
    voice_wait_caps_at_capture_span: bool = False,
) -> tuple[float, float, float]:
    """Retourne (eff_wait, cap_delay, cap_win).

    Si ``voice_wait_caps_at_capture_span`` est True et ``capture_window_sec`` > 0, ``eff_wait`` vaut
    exactement ``capture_delay + capture_window`` : après cette durée sans voix, la phase timeout
    (raccrochage côté scénario). Sinon, ``eff_wait = max(wait_answer_or_voice_sec, delay+fenêtre)``.
    """
    cap_delay = max(0.0, float(capture_delay_sec))
    cap_win = max(0.0, float(capture_window_sec))
    need_vrx_sec = cap_delay + cap_win if cap_win > 0.0 else 0.0
    if voice_wait_caps_at_capture_span and need_vrx_sec > 0.0:
        eff_wait = need_vrx_sec
        logger.info(
            "Attente voix plafonnée à {:.1f}s (= {:.1f}s delay + {:.1f}s fenêtre) — au-delà, timeout si pas de voix",
            eff_wait,
            cap_delay,
            cap_win,
        )
    else:
        eff_wait = max(float(wait_answer_or_voice_sec), need_vrx_sec)
        if eff_wait > float(wait_answer_or_voice_sec):
            logger.info(
                "Durée VRX étendue à {:.1f}s (capture delay {:.1f}s + fenêtre {:.1f}s)",
                eff_wait,
                cap_delay,
                cap_win,
            )
    return eff_wait, cap_delay, cap_win
