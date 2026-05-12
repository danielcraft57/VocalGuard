#!/usr/bin/env python3
"""
Sonde « live STT » (style answer_metrics_probe) :

- compose un numéro
- attend décroché ou activité voix (même pipeline VRX/métriques que answer_metrics_probe)
- ré-ouvre VRX en voix et lance Vosk dans un thread (8 kHz)
- affiche en CLI ce qui est reconnu (partials + phrases finalisées)
- écrit un ``transcript.srt`` au fil de l’eau (flush périodique), puis recalé sur la **1re tonalité**
  du WAV (comme ``t_first_ring`` du rapport ``answer_metrics_probe``) ; le **WAV** est tronqué au même
  instant pour que l’audio et le SRT partagent la même origine t≈0.

But : tester Vosk sur un appel réel en parlant et en voyant le texte apparaître.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from typing import Callable
import time
import wave
from datetime import datetime
from pathlib import Path

from loguru import logger

_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labaudio.vosk_lab import (
    DEFAULT_PROFILE_PATH,
    FRENCH_MODELS,
    print_models_catalog,
    resolve_vosk_model_dir,
    run_configure_only_flow,
)
from labaudio.vosk_stt import (
    VoskRealtimeWorker,
    format_timestamp_sub,
    offset_timed_utterances,
    preload_vosk_model,
    pump_vrx_pcm16_to_vosk,
    write_subrip,
)
from labcore.answer_wait_common import (
    AnswerWaitConfigError,
    effective_vrx_timeout,
    run_answer_wait_phase,
)
from labcore.capture_wav_report import analyze_answer_wav
from labcore.live_audio import u8_pcm_to_s16le
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.call_control import CallController, HangupStyle
from labcore.call_watch import wait_remote_line_end_optional
from labcore.hangup import turbo_hangup


def _one_line_display(s: str) -> str:
    """Une seule ligne pour terminal / pas de retours chariot parasites."""
    return " ".join((s or "").replace("\n", " ").replace("\r", " ").split())


def _terminal_columns() -> int:
    try:
        return max(48, shutil.get_terminal_size((100, 20)).columns)
    except OSError:
        return 100


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compose + VRX (sonde) + Vosk live (thread) + transcript.srt en temps réel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Modèles Vosk (FR) :\n"
            "  python scripts/modem_lab/cli.py answer-vosk-live-probe -- --vosk-list-models\n"
            "  python scripts/modem_lab/cli.py answer-vosk-live-probe -- --vosk-configure-only --vosk-model-slug small-fr\n"
            f"Profil par défaut : {DEFAULT_PROFILE_PATH}\n"
        ),
    )
    add_modem_args(p, need_number=False)
    p.add_argument("--number", required=False, help="Numéro à appeler (requis sauf configure/list).")

    # Vosk
    p.add_argument("--vosk-model", type=Path, default=None, help="Répertoire du modèle Vosk (prioritaire).")
    p.add_argument("--vosk-model-slug", choices=sorted(FRENCH_MODELS.keys()), default=None)
    p.add_argument("--vosk-profile", type=Path, default=DEFAULT_PROFILE_PATH)
    p.add_argument("--vosk-cache-dir", type=Path, default=None)
    p.add_argument("--vosk-save-profile", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--vosk-interactive", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument(
        "--preload-vosk-model",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Précharge le modèle Vosk avant l'appel (recommandé pour les gros modèles).",
    )
    p.add_argument("--vosk-list-models", action="store_true")
    p.add_argument(
        "--vosk-download-all-fr",
        action="store_true",
        help="Télécharge tous les modèles FR du catalogue (alphacephei) dans --vosk-cache-dir puis quitte.",
    )
    p.add_argument("--vosk-configure-only", action="store_true")

    # Answer/voice wait (copié de answer_metrics_probe)
    p.add_argument("--wait-answer-or-voice-sec", type=float, default=20.0)
    p.add_argument("--post-answer-observe-sec", type=float, default=0.0)
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

    # Capture WAV optionnelle (utile pour debug)
    p.add_argument("--record-wav-from-start", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--record-wav-mode", choices=("inline", "thread"), default="inline")
    p.add_argument("--record-wav-out", type=Path, default=Path("scripts/modem_lab/generated/answer_vosk_live_probe/capture.wav"))
    p.add_argument("--record-wav-sec", type=float, default=-1.0)
    p.add_argument(
        "--capture-delay-sec",
        type=float,
        default=0.0,
        help="Début de la fenêtre métriques/WAV (si activés) après ouverture VRX — identique answer_metrics_probe.",
    )
    p.add_argument(
        "--capture-window-sec",
        type=float,
        default=0.0,
        help="Durée fenêtre capture (0 = pas de maintien calibrage). Avec >0, coupler à --wait-full-capture-window.",
    )
    p.add_argument(
        "--extend-wait-beyond-capture",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Si oui : timeout VRX peut dépasser delay+fenêtre (comme metrics_voicemail).",
    )
    p.add_argument(
        "--wait-full-capture-window",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Si oui et --capture-window-sec>0 : garde VRX jusqu'à la fin de la fenêtre (sonde complète) "
            "avant le STT. Défaut **non** : quitte dès voix/décroché pour démarrer Vosk plus tôt."
        ),
    )

    # Live STT
    p.add_argument("--listen-sec", type=float, default=40.0, help="Durée max d’écoute STT après décroché/voix.")
    p.add_argument(
        "--stop-on-idle-sec",
        type=float,
        default=4.0,
        help="Stop STT si aucun chunk VRX reçu pendant N secondes (0 = désactiver).",
    )
    p.add_argument("--subtitle-flush-sec", type=float, default=0.7, help="Intervalle de réécriture transcript.srt.")
    p.add_argument(
        "--subtitle-timeline-offset-sec",
        type=float,
        default=0.0,
        help=(
            "Ajouté aux horodatages SRT après recalage éventuel sur la 1re tonalité "
            "(ex. correction fine vs rapport métriques)."
        ),
    )
    p.add_argument(
        "--srt-origin-first-ring",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Après l’appel : analyse le WAV STT (même heuristique que answer_metrics_probe) ; "
            "réécrit le SRT et **tronque le WAV** pour que t≈0 = 1re tonalité (même repère que le STT). "
            "Désactiver avec --no-srt-origin-first-ring."
        ),
    )
    p.add_argument(
        "--vosk-feed-during-wait",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Pendant l’attente décroché/voix, envoie chaque chunk VRX au modèle Vosk. "
            "Indispensable pour transcrire l’annonce « aucun message » avant le menu SVI."
        ),
    )
    p.add_argument(
        "--vosk-wait-hook-respect-capture-gate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Pendant l’attente : n’envoie au Vosk / au WAV capture que dans la même fenêtre "
            "que les métriques (après --capture-delay-sec, etc.), comme le WAV de answer_metrics_probe. "
            "Désactivé par défaut : sinon l’audio avant le délai n’atteint pas le STT (perte annonce si delay>0)."
        ),
    )
    p.add_argument("--print-partials", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--dated-outfiles", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--transcript-dir", type=Path, default=None, help="Dossier de sortie (défaut: dossier session).")

    # Détection fin de ligne distante (comme answer_metrics_probe)
    p.add_argument(
        "--wait-remote-hangup-sec",
        type=float,
        default=0.0,
        help="Après STT : attendre la fin de ligne distante via VRX (défaut 0 = sauter).",
    )
    p.add_argument(
        "--remote-hangup-dcd-log-sec",
        type=float,
        default=18.0,
        help="Intervalle min entre deux logs DCD pendant l’attente fin de ligne.",
    )
    return p.parse_args()


async def _subtitle_flusher(
    *,
    worker: VoskRealtimeWorker,
    out_srt: Path,
    flush_sec: float,
    stop_event: asyncio.Event,
    timeline_offset_sec: float,
) -> None:
    last_n = -1
    while not stop_event.is_set():
        uts = worker.snapshot_utterances()
        if len(uts) != last_n and uts:
            write_subrip(out_srt, offset_timed_utterances(uts, float(timeline_offset_sec)))
            last_n = len(uts)
        await asyncio.sleep(max(0.15, float(flush_sec)))
    # flush final
    uts = worker.snapshot_utterances()
    if uts:
        write_subrip(out_srt, offset_timed_utterances(uts, float(timeline_offset_sec)))


async def run() -> int:
    args = parse_args()

    if bool(args.vosk_list_models):
        print_models_catalog()
        return 0

    if bool(args.vosk_download_all_fr):
        return run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=None,
            interactive=False,
            list_only=False,
            download_all_fr=True,
        )

    if bool(args.vosk_configure_only):
        return run_configure_only_flow(
            profile_path=Path(args.vosk_profile),
            cache_root=Path(args.vosk_cache_dir) if args.vosk_cache_dir else None,
            model_slug=args.vosk_model_slug,
            interactive=bool(args.vosk_interactive),
            list_only=False,
        )

    if not args.number:
        logger.error(
            "--number est requis (sauf --vosk-configure-only, --vosk-list-models ou --vosk-download-all-fr)."
        )
        return 2

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
            "Modèle Vosk introuvable. Utilisez --vosk-model-slug / --vosk-model ou lancez une fois --vosk-configure-only."
        )
        return 3
    preloaded_model = None
    if bool(args.preload_vosk_model):
        try:
            logger.info("Préchargement modèle Vosk: {}", model_dir)
            t_pre = time.monotonic()
            preloaded_model = preload_vosk_model(Path(model_dir), quiet=True)
            logger.info("Modèle Vosk préchargé en {:.1f}s", time.monotonic() - t_pre)
        except Exception as e:
            logger.warning("Préchargement Vosk échoué (fallback chargement thread): {}", e)
            preloaded_model = None

    # dossier sortie
    capture_dir: Path | None = None
    if bool(args.dated_outfiles):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        capture_dir = Path("scripts/modem_lab/generated/answer_vosk_live_probe") / ts
        capture_dir.mkdir(parents=True, exist_ok=True)
        args.record_wav_out = capture_dir / "capture.wav"
        if args.transcript_dir is None:
            args.transcript_dir = capture_dir
        logger.info("Dossier session: {}", capture_dir)
    if args.transcript_dir is None:
        args.transcript_dir = Path("scripts/modem_lab/generated/answer_vosk_live_probe")
        args.transcript_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = Path(args.transcript_dir) / "transcript.srt"

    modem = build_modem(args)
    ctl = CallController(modem)
    try:
        if not await modem.initialize():
            logger.error("Échec initialisation modem")
            return 4
        ok_prep = await ctl.prepare_voice_for_blind_dial()
        if not ok_prep:
            logger.error("Échec préparation voix avant composition")
            return 5

        ok_dial, raw = await ctl.dial(args.number, blind=bool(args.voice_blind_dial))
        logger.info("Dial {} -> ok={} raw={}", args.number, ok_dial, raw or "(vide)")
        if not ok_dial:
            return 6

        eff_wait, cap_delay, cap_win = effective_vrx_timeout(
            float(args.wait_answer_or_voice_sec),
            float(args.capture_delay_sec),
            float(args.capture_window_sec),
            voice_wait_caps_at_capture_span=not bool(args.extend_wait_beyond_capture),
        )
        report_session_extra = {
            "scenario": "answer_vosk_live_probe",
            "wait_full_capture_window": bool(args.wait_full_capture_window),
            "extend_wait_beyond_capture": bool(args.extend_wait_beyond_capture),
            "subtitle_timeline_offset_sec": float(args.subtitle_timeline_offset_sec),
            "vosk_feed_during_wait": bool(args.vosk_feed_during_wait),
            "vosk_wait_hook_respect_capture_gate": bool(args.vosk_wait_hook_respect_capture_gate),
            "srt_origin_first_ring": bool(args.srt_origin_first_ring),
        }

        # Même timeline que le STT : PCM u8 depuis le premier chunk envoyé à Vosk (attente + pump).
        capture_raw_u8 = bytearray()

        last_partial: dict[str, str] = {"t": ""}

        def on_partial(t: str) -> None:
            if not bool(args.print_partials):
                return
            last_partial["t"] = t

        worker = VoskRealtimeWorker(
            Path(model_dir),
            sample_rate=8000,
            on_partial=on_partial,
            preloaded_model=preloaded_model,
        )

        def _vosk_set_log_level() -> None:
            try:
                from vosk import SetLogLevel  # type: ignore

                SetLogLevel(-1)
            except Exception:
                pass

        wait_pcm_hook: Callable[[bytes], None] | None = None
        if bool(args.vosk_feed_during_wait):
            _vosk_set_log_level()
            worker.start()

            def _feed_wait_pcm_u8(chunk: bytes) -> None:
                if chunk:
                    capture_raw_u8.extend(chunk)
                    worker.push_pcm16(u8_pcm_to_s16le(chunk))

            wait_pcm_hook = _feed_wait_pcm_u8
            logger.info("Vosk : flux PCM de la phase attente aussi envoyé au STT (annonce avant menu SVI).")

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
                # La capture WAV de ce scénario doit suivre la fenêtre STT,
                # pas la phase d'attente décroché/voix.
                record_wav_from_start=False,
                record_wav_mode=str(args.record_wav_mode),
                record_wav_out=Path(args.record_wav_out),
                record_wav_sec=float(args.record_wav_sec),
                metrics_out=None,
                metrics_thread=True,
                metrics_flush_sec=0.5,
                auto_report=False,
                report_frame_ms=80.0,
                report_hop_ms=40.0,
                exit_wait_on_voice=not bool(args.wait_full_capture_window),
                report_session_extra={
                    **report_session_extra,
                    "vosk_slug": vosk_slug or "",
                },
                on_vrx_pcm_u8=wait_pcm_hook,
                vrx_hook_only_when_capturing=bool(args.vosk_wait_hook_respect_capture_gate),
            )
        except AnswerWaitConfigError as e:
            logger.error("{}", e)
            if wait_pcm_hook is not None:
                worker.close_input()
                try:
                    worker.join_utterances(timeout=5.0)
                except Exception:
                    pass
            return 7

        logger.info("Attente décroché/voix -> ready={} reason={}", ready, why)
        if not ready:
            if wait_pcm_hook is not None:
                worker.close_input()
                try:
                    worker.join_utterances(timeout=5.0)
                except Exception:
                    pass
            return 8

        # VRX : on ré-ouvre en mode voix pour la suite du STT (même worker Vosk si déjà alimenté)
        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass
        opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=True)
        if not opened:
            logger.error("Impossible d’ouvrir VRX pour l’écoute STT")
            if wait_pcm_hook is not None:
                worker.close_input()
                try:
                    worker.join_utterances(timeout=5.0)
                except Exception:
                    pass
            return 9

        if wait_pcm_hook is None:
            _vosk_set_log_level()
            worker.start()

        last_final_idx = 0

        stop_flush = asyncio.Event()
        flush_task = asyncio.create_task(
            _subtitle_flusher(
                worker=worker,
                out_srt=transcript_path,
                flush_sec=float(args.subtitle_flush_sec),
                stop_event=stop_flush,
                timeline_offset_sec=float(args.subtitle_timeline_offset_sec),
            )
        )

        t0 = time.monotonic()
        try:
            logger.info("STT live (vosk) démarré: {} (slug={})", model_dir, vosk_slug or "—")
            logger.info("Sous-titres: {}", transcript_path)

            def _render_partial_line(text: str) -> None:
                # Une seule ligne physique : évite les « trous » si le texte wrappe (\\r ne nettoie qu’une ligne).
                s = _one_line_display(text).strip()
                if not s:
                    return
                cols = _terminal_columns()
                elapsed = max(0.0, time.monotonic() - t0)
                prefix = f"[PARTIAL {format_timestamp_sub(elapsed)}] "
                max_body = max(12, cols - len(prefix) - 1)
                if len(s) > max_body:
                    s = s[: max(max_body - 3, 1)] + "..."
                line = prefix + s
                pad = max(0, cols - len(line) - 1)
                sys.stdout.write("\r" + (" " * (cols - 1)) + "\r" + line + (" " * pad))
                sys.stdout.flush()

            def _clear_partial_line() -> None:
                cols = _terminal_columns()
                sys.stdout.write("\r" + (" " * (cols - 1)) + "\r")
                sys.stdout.flush()

            last_partial_printed = ""

            def _capture_chunk_u8(chunk: bytes) -> None:
                if chunk:
                    capture_raw_u8.extend(chunk)

            pump_task = asyncio.create_task(
                pump_vrx_pcm16_to_vosk(
                    modem,
                    worker,
                    max_seconds=max(1.0, float(args.listen_sec)),
                    max_idle_sec=(float(args.stop_on_idle_sec) if float(args.stop_on_idle_sec) > 0.0 else None),
                    on_chunk_u8=_capture_chunk_u8,
                )
            )
            while not pump_task.done():
                uts = worker.snapshot_utterances()
                if len(uts) > last_final_idx:
                    _clear_partial_line()
                    cols = _terminal_columns()
                    t_off = float(args.subtitle_timeline_offset_sec)
                    for u in uts[last_final_idx:]:
                        body = _one_line_display(u.text).strip()
                        head = (
                            f"[FINAL {format_timestamp_sub(u.start_sec + t_off)} -> "
                            f"{format_timestamp_sub(u.end_sec + t_off)}] "
                        )
                        room = max(24, cols - len(head) - 1)
                        if len(body) > room:
                            body = body[: max(room - 3, 1)] + "..."
                        print(head + body, flush=True)
                    last_final_idx = len(uts)
                p = last_partial.get("t") or ""
                if p:
                    # n’afficher que si le partial change réellement
                    p1 = _one_line_display(p).strip()
                    if p1 and p1 != last_partial_printed:
                        _render_partial_line(p)
                        last_partial_printed = p1
                    last_partial["t"] = ""
                await asyncio.sleep(0.20)

            stop_reason = await pump_task
            if stop_reason == "remote_line_end":
                logger.info("Écoute STT interrompue : fin de ligne distante.")
            elif stop_reason == "idle_timeout":
                logger.info(
                    "Écoute STT interrompue : inactivité VRX > {:.1f}s (raccrochage probable).",
                    float(args.stop_on_idle_sec),
                )
        finally:
            try:
                sys.stdout.write("\n")
                sys.stdout.flush()
            except Exception:
                pass
            worker.close_input()
            try:
                worker.join_utterances(timeout=45.0)
            except Exception as e:
                logger.exception("Vosk join: {}", e)
            stop_flush.set()
            try:
                await flush_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

            # WAV : même PCM u8 que celui vu par Vosk (phase attente si --vosk-feed-during-wait, puis pump).
            try:
                out_wav = Path(args.record_wav_out)
                out_wav.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(out_wav), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(1)  # u8 PCM modem
                    wf.setframerate(8000)
                    wf.writeframes(bytes(capture_raw_u8))
                logger.info("WAV STT: {} ({} octets PCM)", out_wav, len(capture_raw_u8))
            except Exception as e:
                logger.warning("Écriture WAV STT échouée: {}", e)

            if bool(args.srt_origin_first_ring):
                try:
                    uts_final = worker.snapshot_utterances()
                    wav_p = Path(args.record_wav_out)
                    # Au moins ~0,5 s de PCM u8 mono pour que l’analyse tonalité soit fiable.
                    if uts_final and wav_p.is_file() and wav_p.stat().st_size > 4000:
                        # Même fenêtre 80/40 ms que le rapport auto answer_metrics_probe.
                        rep = analyze_answer_wav(wav_p, frame_ms=80.0, hop_ms=40.0)
                        if rep.get("error"):
                            logger.debug("SRT recalage tonalité: analyse WAV: {}", rep.get("error"))
                        else:
                            tr = rep.get("t_first_ring")
                            if tr is not None:
                                off = float(args.subtitle_timeline_offset_sec) - float(tr)
                                write_subrip(
                                    transcript_path,
                                    offset_timed_utterances(uts_final, off),
                                )
                                logger.info(
                                    "SRT aligné sur 1re tonalité (t_first_ring={}s), offset combiné={:.3f}s "
                                    "(dont décalage CLI {:.3f}s).",
                                    tr,
                                    off,
                                    float(args.subtitle_timeline_offset_sec),
                                )
                                # WAV : même origine que le SRT (retirer le préambule avant la 1re tonalité).
                                trim_idx = int(round(float(tr) * 8000.0))
                                trim_idx = max(0, min(trim_idx, len(capture_raw_u8)))
                                if trim_idx > 0 and trim_idx < len(capture_raw_u8):
                                    tail_pcm = bytes(capture_raw_u8[trim_idx:])
                                    with wave.open(str(wav_p), "wb") as wf:
                                        wf.setnchannels(1)
                                        wf.setsampwidth(1)
                                        wf.setframerate(8000)
                                        wf.writeframes(tail_pcm)
                                    logger.info(
                                        "WAV aligné sur 1re tonalité : {:.3f}s ({:.0f} octets) retirés au début.",
                                        float(tr),
                                        float(trim_idx),
                                    )
                                elif trim_idx >= len(capture_raw_u8):
                                    logger.warning(
                                        "WAV : t_first_ring={}s dépasse la durée capture — pas de troncature.",
                                        tr,
                                    )
                            else:
                                logger.info(
                                    "SRT : pas de t_first_ring sur le WAV — horodatages inchangés "
                                    "(hors --subtitle-timeline-offset-sec appliqué pendant le flush)."
                                )
                except Exception as e:
                    logger.warning("SRT recalage sur 1re tonalité échoué: {}", e)

        logger.info("Durée écoute STT: {:.1f}s", time.monotonic() - t0)

        # En pratique, la détection « remote_line_end » pendant le pump peut rater selon modem/ligne.
        # On refait une phase dédiée comme dans answer_metrics_probe.
        if float(args.wait_remote_hangup_sec) > 0.0:
            # Fermer le VRX utilisé par le STT avant de ré-ouvrir pour la détection.
            try:
                await modem.end_outgoing_vrx_stream()
            except Exception:
                pass
            try:
                task = asyncio.create_task(
                    wait_remote_line_end_optional(
                        modem,
                        timeout_sec=float(args.wait_remote_hangup_sec),
                        already_in_voice_mode=True,
                        dcd_log_heartbeat_sec=float(args.remote_hangup_dcd_log_sec),
                        session_note="answer_vosk_live_probe post-STT",
                    ),
                    name="wait_remote_line_end_optional",
                )
                detected, reason = await asyncio.wait_for(task, timeout=float(args.wait_remote_hangup_sec) + 5.0)
                if detected is not None:
                    logger.info("Fin de ligne distante détectée -> detected={} reason={}", detected, reason)
            except asyncio.TimeoutError:
                logger.info("Fin de ligne distante: timeout (wait_for).")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Fin de ligne distante: étape interrompue/échouée: {}", e)
        return 0
    finally:
        try:
            await turbo_hangup(modem)
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("answer_vosk_live_probe")
    raise SystemExit(asyncio.run(run()))

