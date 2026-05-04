#!/usr/bin/env python3
"""
Scénario sortant « démarchage » : même pipeline de sonde que ``metrics_voicemail`` (VRX, métriques,
capture optionnelle), puis lecture d’un **message d’ouverture** (WAV), écoute du correspondant avec
**Vosk dans un thread**, export **SUB / WebVTT**, et optionnellement lecture d’une **réponse** du pack
audio si une intention (patterns JSON) matche la transcription.

Prérequis
---------
- Modèle Vosk français : ``--vosk-model-slug small-fr`` (télécharge dans ``generated/vosk_models/``),
  ou ``--vosk-model`` / ``VOSK_MODEL_PATH``, ou profil ``generated/vosk_lab_profile.json``.
  Liste des slugs : ``--vosk-list-models``. Configuration seule (sans modem) : ``--vosk-configure-only``.
- WAV d’ouverture : ``--greeting-wav`` ou ``--audio-pack-dir`` + ``greeting_01.wav`` (voir
  ``labaudio/generate_intent_pack.py`` à partir de ``data/intents_prospection_flow.json``).

Les sous-titres sont alignés sur les timings internes Vosk (phrases successives).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labaudio.intent_wav_pack import match_intent_reply_wav
from labaudio.vosk_lab import (
    DEFAULT_PROFILE_PATH,
    FRENCH_MODELS,
    print_models_catalog,
    resolve_vosk_model_dir,
    run_configure_only_flow,
)
from labaudio.vosk_stt import (
    VoskRealtimeWorker,
    pump_vrx_pcm16_to_vosk,
    write_subrip,
    write_webvtt,
)
from labcore.answer_wait_common import (
    AnswerWaitConfigError,
    effective_vrx_timeout,
    run_answer_wait_phase,
)
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.call_control import CallController
from labcore.call_watch import wait_remote_line_end_optional
from labcore.hangup import turbo_hangup
from labscenarios.metrics_voicemail import _play_trigger_ok, _play_voice_clip

_PROMPT_PAUSE_EPS_SEC = 1e-3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prospection sortante : sonde métrique + greeting WAV + STT Vosk (SUB/VTT) + réponse intent optionnelle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modèles Vosk (FR) : voir --vosk-list-models. Exemples :\n"
            "  python scripts/modem_lab/cli.py prospection-outbound -- --vosk-configure-only --vosk-model-slug small-fr\n"
            "  python scripts/modem_lab/cli.py prospection-outbound -- --port COM6 --number +33... "
            "--vosk-model-slug small-fr --greeting-wav path/to/greeting_01.wav\n"
            f"  Profil par défaut : {DEFAULT_PROFILE_PATH}"
        ),
    )
    add_modem_args(p, need_number=False)
    p.add_argument(
        "--number",
        default=None,
        help="Numéro à appeler (requis sauf avec --vosk-configure-only ou --vosk-list-models).",
    )

    p.add_argument(
        "--vosk-model",
        type=Path,
        default=None,
        help="Répertoire du modèle Vosk (prioritaire sur slug / profil / env).",
    )
    p.add_argument(
        "--vosk-model-slug",
        choices=sorted(FRENCH_MODELS.keys()),
        default=None,
        help="Télécharge ou réutilise un modèle du catalogue dans --vosk-cache-dir.",
    )
    p.add_argument(
        "--vosk-profile",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Fichier JSON persistant (slug + chemin modèle + cache).",
    )
    p.add_argument(
        "--vosk-cache-dir",
        type=Path,
        default=None,
        help="Répertoire racine des modèles téléchargés (défaut : generated/vosk_models).",
    )
    p.add_argument(
        "--vosk-save-profile",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enregistrer le modèle résolu dans --vosk-profile (défaut : oui).",
    )
    p.add_argument(
        "--vosk-interactive",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Menu interactif (tty) si aucun modèle résolu au démarrage.",
    )
    p.add_argument(
        "--vosk-list-models",
        action="store_true",
        help="Affiche le catalogue français puis quitte (pas d’appel).",
    )
    p.add_argument(
        "--vosk-configure-only",
        action="store_true",
        help="Télécharge le modèle choisi, met à jour le profil, quitte (pas de modem).",
    )
    p.add_argument(
        "--greeting-wav",
        type=Path,
        default=None,
        help="WAV d’ouverture (8 kHz mono). Prioritaire sur le pack.",
    )
    p.add_argument(
        "--audio-pack-dir",
        type=Path,
        default=None,
        help="Dossier contenant greeting_01.wav (si --greeting-wav absent).",
    )
    p.add_argument("--listen-sec", type=float, default=28.0, help="Durée max d’écoute STT après le greeting.")
    p.add_argument(
        "--subtitle-format",
        choices=("none", "sub", "vtt", "both"),
        default="both",
        help="Export transcription : SubRip, WebVTT, les deux, ou aucun.",
    )
    p.add_argument(
        "--intents-json",
        type=Path,
        default=None,
        help="JSON des intents (ex. data/intents_prospection_flow.json) pour --try-intent-reply.",
    )
    p.add_argument(
        "--try-intent-reply",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Après STT : jouer le WAV du 1er intent dont un pattern matche (pack_dir).",
    )

    p.add_argument(
        "--dated-outfiles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Horodatage generated/prospection_outbound/<ts>/ (metrics, capture, sous-titres).",
    )
    p.add_argument(
        "--transcript-dir",
        type=Path,
        default=None,
        help="Dossier des .sub/.vtt (défaut : dossier session si --dated-outfiles).",
    )

    p.add_argument(
        "--play-after-reason",
        choices=("voice_activity", "any_ready"),
        default="voice_activity",
    )
    p.add_argument("--wait-answer-or-voice-sec", type=float, default=45.0)
    p.add_argument("--post-answer-observe-sec", type=float, default=0.0)
    p.add_argument("--voice-blind-dial", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--answer-on-voice-activity", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--answer-on-energy-fallback", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-voice-trigger-sec", type=float, default=0.0)
    p.add_argument("--vad-threshold", type=float, default=22.0)
    p.add_argument("--vad-min-speech-ms", type=float, default=420.0)
    p.add_argument("--vad-hangover-ms", type=float, default=500.0)
    p.add_argument("--energy-score-min", type=float, default=24.0)
    p.add_argument("--energy-jitter-min", type=float, default=8.0)
    p.add_argument("--energy-score-span-min", type=float, default=6.0)
    p.add_argument("--energy-jitter-span-min", type=float, default=2.5)
    p.add_argument("--tone-reject", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--tone-reject-zcr-min", type=float, default=0.03)
    p.add_argument("--tone-reject-zcr-max", type=float, default=0.30)
    p.add_argument("--tone-reject-periodicity-max", type=float, default=0.90)
    p.add_argument("--metrics-thread", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--metrics-flush-sec", type=float, default=0.5)
    p.add_argument("--record-wav-from-start", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--record-wav-mode", choices=("inline", "thread"), default="inline")
    p.add_argument(
        "--record-wav-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/prospection_outbound/capture.wav"),
    )
    p.add_argument("--record-wav-sec", type=float, default=-1.0)
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/prospection_outbound/metrics.csv"),
    )
    p.add_argument("--capture-delay-sec", type=float, default=7.5)
    p.add_argument("--capture-window-sec", type=float, default=20.0)
    p.add_argument("--wait-full-capture-window", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--extend-wait-beyond-capture", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--auto-report", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--report-frame-ms", type=float, default=80.0)
    p.add_argument("--report-hop-ms", type=float, default=40.0)
    p.add_argument("--pause-before-prompt-sec", type=float, default=0.0)
    p.add_argument(
        "--prompt-play-prefer-already-voice",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    p.add_argument(
        "--half-duplex-uplink-for-prompt",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    p.add_argument("--wait-remote-hangup-sec", type=float, default=20.0)
    p.add_argument("--remote-hangup-dcd-log-sec", type=float, default=18.0)

    return p.parse_args()


def _resolve_greeting_wav(args: argparse.Namespace) -> Path | None:
    if args.greeting_wav is not None and Path(args.greeting_wav).is_file():
        return Path(args.greeting_wav)
    if args.audio_pack_dir is not None:
        cand = Path(args.audio_pack_dir) / "greeting_01.wav"
        if cand.is_file():
            return cand
    return None


async def run(parser_args: argparse.Namespace | None = None) -> int:
    """
    Codes : 0 OK, 1 init modem, 2 prep voix, 3 dial, 4 config capture, 5 pas de détection,
    6 incompatible play-after-reason, 7 greeting, 8 vosk, 9 réponse intent.
    """
    args = parser_args if parser_args is not None else parse_args()

    if bool(args.vosk_list_models):
        print_models_catalog()
        return 0

    if bool(args.vosk_configure_only):
        return run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=args.vosk_model_slug,
            interactive=bool(args.vosk_interactive),
            list_only=False,
        )

    if not args.number:
        logger.error("--number est requis (sauf --vosk-configure-only ou --vosk-list-models).")
        return 1

    model_dir, vosk_slug = resolve_vosk_model_dir(
        explicit_path=Path(args.vosk_model) if args.vosk_model else None,
        model_slug=args.vosk_model_slug,
        profile_path=Path(args.vosk_profile),
        cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
        env_path=None,
        interactive=bool(args.vosk_interactive),
        save_profile_flag=bool(args.vosk_save_profile),
    )
    if model_dir is None:
        logger.error(
            "Modèle Vosk introuvable. Indiquez --vosk-model-slug (voir --vosk-list-models), "
            "--vosk-model, --vosk-interactive sur un terminal, ou configurez VOSK_MODEL_PATH / "
            "lancez une fois --vosk-configure-only."
        )
        return 8
    logger.info("STT Vosk : {} (slug={})", model_dir, vosk_slug or "—")

    greeting = _resolve_greeting_wav(args)
    if greeting is None:
        logger.error("WAV greeting introuvable : fournir --greeting-wav ou --audio-pack-dir avec greeting_01.wav.")
        return 7

    session_dir: Path | None = None
    if bool(args.dated_outfiles):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        session_dir = Path("scripts/modem_lab/generated/prospection_outbound") / ts
        session_dir.mkdir(parents=True, exist_ok=True)
        args.metrics_out = session_dir / "metrics.csv"
        args.record_wav_out = session_dir / "capture.wav"
        logger.info("Dossier session: {}", session_dir)

    if args.transcript_dir is not None:
        transcript_dir = Path(args.transcript_dir)
    elif session_dir is not None:
        transcript_dir = session_dir
    else:
        transcript_dir = Path("scripts/modem_lab/generated/prospection_outbound")
        transcript_dir.mkdir(parents=True, exist_ok=True)

    modem = build_modem(args)
    ctl = CallController(modem)

    pack_dir = Path(args.audio_pack_dir) if args.audio_pack_dir else greeting.parent

    try:
        if not await modem.initialize():
            logger.error("Échec initialisation modem")
            return 1
        if not await ctl.prepare_voice_for_blind_dial():
            logger.error("Échec préparation voix avant composition")
            return 2
        ok_dial, raw = await ctl.dial(args.number, blind=bool(args.voice_blind_dial))
        logger.info("Dial {} -> ok={} raw={}", args.number, ok_dial, raw or "(vide)")
        if not ok_dial:
            return 3

        eff_wait, cap_delay, cap_win = effective_vrx_timeout(
            float(args.wait_answer_or_voice_sec),
            float(args.capture_delay_sec),
            float(args.capture_window_sec),
            voice_wait_caps_at_capture_span=not bool(args.extend_wait_beyond_capture),
        )
        report_session_extra: dict[str, Any] = {
            "scenario": "prospection_outbound",
            "wait_full_capture_window": bool(args.wait_full_capture_window),
            "extend_wait_beyond_capture": bool(args.extend_wait_beyond_capture),
        }
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
                exit_wait_on_voice=not bool(args.wait_full_capture_window),
                report_session_extra=report_session_extra,
            )
        except AnswerWaitConfigError as e:
            logger.error("{}", e)
            return 4

        logger.info("Attente décroché/voix -> ready={} reason={}", ready, why)
        if not ready:
            logger.error("Pas de détection avant timeout — pas de greeting")
            return 5
        if not _play_trigger_ok(why, str(args.play_after_reason)):
            logger.error("Reason={} incompatible avec --play-after-reason={}", why, args.play_after_reason)
            return 6

        pause_prompt = max(0.0, float(args.pause_before_prompt_sec))
        if pause_prompt > _PROMPT_PAUSE_EPS_SEC:
            await asyncio.sleep(pause_prompt)

        prefer_voice = bool(args.prompt_play_prefer_already_voice)
        try_hd = bool(args.half_duplex_uplink_for_prompt)
        played = await _play_voice_clip(
            modem,
            greeting,
            prefer_voice=prefer_voice,
            try_half_duplex=try_hd,
            label="Greeting",
        )
        if not played:
            logger.error("Échec lecture greeting")
            return 7
        await asyncio.sleep(0.2)

        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass

        opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=True)
        if not opened:
            logger.error("Impossible de rouvrir VRX pour l’écoute STT")
            return 8

        worker = VoskRealtimeWorker(Path(model_dir), sample_rate=8000)
        worker.start()
        stop_reason = None
        try:
            stop_reason = await pump_vrx_pcm16_to_vosk(
                modem,
                worker,
                max_seconds=max(1.0, float(args.listen_sec)),
            )
        finally:
            worker.close_input()
            try:
                utterances = worker.join_utterances(timeout=45.0)
            except Exception as e:
                logger.exception("Vosk join: {}", e)
                utterances = []

        if stop_reason == "remote_line_end":
            logger.info("Écoute STT interrompue : fin de ligne distante.")

        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass

        full_text = " ".join(u.text for u in utterances).strip()
        logger.info("Transcription (résumé): {}", full_text[:500] or "(vide)")

        if args.subtitle_format in ("sub", "both") and utterances and transcript_dir is not None:
            sub_path = transcript_dir / "transcript.srt"
            write_subrip(sub_path, utterances)
            logger.info("SubRip écrit: {}", sub_path)
        if args.subtitle_format in ("vtt", "both") and utterances and transcript_dir is not None:
            vtt_path = transcript_dir / "transcript.vtt"
            write_webvtt(vtt_path, utterances)
            logger.info("WebVTT écrit: {}", vtt_path)

        if bool(args.try_intent_reply) and args.intents_json is not None:
            reply = match_intent_reply_wav(full_text, Path(args.intents_json), pack_dir)
            if reply is not None:
                logger.info("Intent match -> lecture {}", reply)
                ok_r = await _play_voice_clip(
                    modem,
                    reply,
                    prefer_voice=True,
                    try_half_duplex=try_hd,
                    label="Réponse intent",
                )
                if not ok_r:
                    logger.warning("Lecture réponse intent échouée")
                    return 9
                await asyncio.sleep(0.15)
            else:
                logger.info("Aucun pattern intent ne matche la transcription — pas de réponse automatique.")

        await wait_remote_line_end_optional(
            modem,
            timeout_sec=float(args.wait_remote_hangup_sec),
            already_in_voice_mode=True,
            dcd_log_heartbeat_sec=float(args.remote_hangup_dcd_log_sec),
            session_note="prospection_outbound post-réponse.",
        )

        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        try:
            await turbo_hangup(modem)
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    try:
        _cli_args = parse_args()
    except SystemExit as _e:
        raise SystemExit(_e.code) from None
    setup_logging("prospection_outbound")
    raise SystemExit(asyncio.run(run(_cli_args)))
