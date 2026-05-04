#!/usr/bin/env python3
"""
Sonde de calibration décroché/voix.

Ce scénario compose un numéro, ouvre l'attente "answer or voice", puis exporte
les métriques audio (raw_score, raw_jitter, spans, active_ms, DCD) dans un CSV.

Avec ``--dated-outfiles`` (défaut), chaque exécution crée un sous-dossier
``generated/answer_metrics_probe/answer_metrics_probe_<horodatage>/`` contenant
``metrics.csv``, ``capture.wav``, et après coup ``report.json`` + ``report.txt``
(résumé ``t_first_ring`` / ``t_last_ring_before_voice`` / ``t_speech_candidate``).

L'enregistrement WAV par défaut est **inline** (même session ``AT+VRX`` que les
métriques). Le mode **thread** (second ``AT+VRX``) reste disponible mais est
souvent incompatible en parallèle.

La logique d'attente / métriques / WAV est dans ``labcore.answer_wait_common``.
La détection « décroché / parole » utilise ``wait_answer_or_voice_activity`` dans
``labcore.call_watch``. Une **écoute optionnelle** de fin de ligne distante après coup repose
sur ``wait_remote_line_end_optional`` (WRX seulement ; pas de nouveau WAV).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.answer_wait_common import (
    AnswerWaitConfigError,
    effective_vrx_timeout,
    run_answer_wait_phase,
)
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.call_control import CallController, HangupStyle
from labcore.call_watch import wait_remote_line_end_optional


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compose puis exporte les métriques de détection décroché/voix vers CSV."
    )
    add_modem_args(p, need_number=True)
    p.add_argument("--wait-answer-or-voice-sec", type=float, default=20.0)
    p.add_argument(
        "--post-answer-observe-sec",
        type=float,
        default=12.0,
        help="Continuer la capture des métriques X sec après le 1er décroché/voix.",
    )
    p.add_argument("--voice-blind-dial", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--answer-on-voice-activity", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--answer-on-energy-fallback", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-voice-trigger-sec", type=float, default=0.0)
    p.add_argument("--vad-threshold", type=float, default=20.0)
    p.add_argument("--vad-min-speech-ms", type=float, default=250.0)
    p.add_argument("--vad-hangover-ms", type=float, default=500.0)
    p.add_argument("--energy-score-min", type=float, default=24.0)
    p.add_argument("--energy-jitter-min", type=float, default=8.0)
    p.add_argument("--energy-score-span-min", type=float, default=6.0)
    p.add_argument("--energy-jitter-span-min", type=float, default=2.5)
    p.add_argument("--tone-reject", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--tone-reject-zcr-min", type=float, default=0.03)
    p.add_argument("--tone-reject-zcr-max", type=float, default=0.30)
    p.add_argument("--tone-reject-periodicity-max", type=float, default=0.90)
    p.add_argument(
        "--dated-outfiles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Crée un sous-dossier horodaté sous generated/answer_metrics_probe/ (metrics.csv, capture.wav).",
    )
    p.add_argument(
        "--metrics-thread",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Ecrit les métriques en temps réel via thread (recommandé pour captures longues).",
    )
    p.add_argument("--metrics-flush-sec", type=float, default=0.5, help="Intervalle de flush CSV du writer thread.")
    p.add_argument(
        "--record-wav-from-start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enregistre la ligne en WAV dès le début de la phase d'attente.",
    )
    p.add_argument(
        "--record-wav-mode",
        choices=("inline", "thread"),
        default="inline",
        help="inline: même VRX que les métriques (recommandé). thread: second enregistrement (risque de conflit série).",
    )
    p.add_argument(
        "--record-wav-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/answer_metrics_probe/answer_metrics_probe.wav"),
        help="Chemin du WAV capturé depuis le début.",
    )
    p.add_argument(
        "--record-wav-sec",
        type=float,
        default=-1.0,
        help="(mode thread) Durée d'enregistrement WAV (<=0: auto = wait + post-observe + 3s).",
    )
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/answer_metrics_probe/answer_metrics_probe.csv"),
        help="Fichier CSV de sortie des métriques.",
    )
    p.add_argument(
        "--capture-delay-sec",
        type=float,
        default=0.0,
        help="Ne collecte métriques/WAV qu'après ce délai (s) depuis l'ouverture VRX.",
    )
    p.add_argument(
        "--capture-window-sec",
        type=float,
        default=0.0,
        help="Durée max de collecte métriques/WAV après le délai (0 = jusqu'à fin timeout).",
    )
    p.add_argument(
        "--auto-report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Génère report.json + report.txt (analyse WAV) à la fin.",
    )
    p.add_argument("--report-frame-ms", type=float, default=80.0, help="Fenêtre analyse rapport (50–100 ms conseillé).")
    p.add_argument("--report-hop-ms", type=float, default=40.0, help="Pas entre fenêtres (recouvrement si < frame).")
    p.add_argument(
        "--wait-remote-hangup-sec",
        type=float,
        default=0.0,
        help=(
            "Après métriques/WAV : écoute VRX pour marqueur de fin (pas de nouvel enregistrement). "
            "0 = sauter (comportement historique). USB sortant : timeout fréquent si DCD absent."
        ),
    )
    p.add_argument(
        "--remote-hangup-dcd-log-sec",
        type=float,
        default=18.0,
        help="Intervalle min entre deux logs DCD pendant wait_remote_hangup.",
    )
    return p.parse_args()


async def run() -> int:
    args = parse_args()
    capture_dir: Path | None = None
    if bool(args.dated_outfiles):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        capture_dir = Path("scripts/modem_lab/generated/answer_metrics_probe") / ts
        capture_dir.mkdir(parents=True, exist_ok=True)
        args.metrics_out = capture_dir / "metrics.csv"
        args.record_wav_out = capture_dir / "capture.wav"
        logger.info("Dossier capture: {}", capture_dir)
    modem = build_modem(args)
    ctl = CallController(modem)
    try:
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1
        ok_prep = await ctl.prepare_voice_for_blind_dial()
        if not ok_prep:
            logger.error("Echec préparation voix avant composition")
            return 2
        ok_dial, raw = await ctl.dial(args.number, blind=bool(args.voice_blind_dial))
        logger.info("Dial {} -> ok={} raw={}", args.number, ok_dial, raw or "(vide)")
        if not ok_dial:
            return 3

        eff_wait, cap_delay, cap_win = effective_vrx_timeout(
            float(args.wait_answer_or_voice_sec),
            float(args.capture_delay_sec),
            float(args.capture_window_sec),
        )

        try:
            ready, why = await run_answer_wait_phase(
                modem,
                eff_wait=eff_wait,
                post_answer_observe_sec=float(args.post_answer_observe_sec),
                capture_delay_sec=cap_delay,
                capture_window_sec=cap_win,
                allow_voice_activity=bool(args.answer_on_voice_activity),
                allow_energy_fallback=bool(args.answer_on_energy_fallback),
                min_voice_trigger_sec=float(args.min_voice_trigger_sec),
                energy_score_min=float(args.energy_score_min),
                energy_jitter_min=float(args.energy_jitter_min),
                energy_score_span_min=float(args.energy_score_span_min),
                energy_jitter_span_min=float(args.energy_jitter_span_min),
                tone_reject_enabled=bool(args.tone_reject),
                tone_reject_zcr_min=float(args.tone_reject_zcr_min),
                tone_reject_zcr_max=float(args.tone_reject_zcr_max),
                tone_reject_periodicity_max=float(args.tone_reject_periodicity_max),
                vad_threshold=float(args.vad_threshold),
                vad_min_speech_ms=float(args.vad_min_speech_ms),
                vad_hangover_ms=float(args.vad_hangover_ms),
                already_in_voice_mode=False,
                record_wav_from_start=bool(args.record_wav_from_start),
                record_wav_mode=str(args.record_wav_mode),
                record_wav_out=Path(args.record_wav_out),
                record_wav_sec=float(args.record_wav_sec),
                metrics_out=Path(args.metrics_out),
                metrics_thread=bool(args.metrics_thread),
                metrics_flush_sec=float(args.metrics_flush_sec),
                auto_report=bool(args.auto_report),
                report_frame_ms=float(args.report_frame_ms),
                report_hop_ms=float(args.report_hop_ms),
                report_session_extra={"scenario": "answer_metrics_probe"},
            )
        except AnswerWaitConfigError as e:
            logger.error("{}", e)
            return 4
        logger.info("Attente décroché/voix -> ready={} reason={}", ready, why)
        hup, hwhy = await wait_remote_line_end_optional(
            modem,
            timeout_sec=float(args.wait_remote_hangup_sec),
            already_in_voice_mode=True,
            dcd_log_heartbeat_sec=float(args.remote_hangup_dcd_log_sec),
            session_note="(métriques/WAV déjà finalisés).",
        )
        if hup is not None:
            logger.info("Attente raccrochage distant -> detected={} reason={}", hup, hwhy)
        return 0
    finally:
        try:
            await ctl.hangup(HangupStyle.TURBO)
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("answer_metrics_probe")
    raise SystemExit(asyncio.run(run()))
