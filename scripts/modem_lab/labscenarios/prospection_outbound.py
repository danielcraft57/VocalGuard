#!/usr/bin/env python3
"""
Scénario sortant « démarchage » : même pipeline de sonde que ``metrics_voicemail`` (VRX, métriques,
capture optionnelle), puis **ouverture** audio, **écoute Vosk** (thread), export **SUB / WebVTT**,
et en option **réponses** depuis un pack WAV aligné sur des intents JSON.

Architecture dialogue (``labcore.prospection_dialogue``)
--------------------------------------------------------
- **Chaîne de responsabilité** : plusieurs ``--intents-json`` (ordre = priorité entre fichiers) ;
  dans chaque fichier, ordre du tableau ``intents`` = priorité entre intentions.
- **Memento** : ``ConversationSnapshot`` enregistre les tours et tags joués (extensible logs / reprise).
- **Ouverture aléatoire** : avec ``--opening-tag`` + pack, tirage d’une variante ``tag_XX.wav`` ;
  sinon si ``--intents-json`` + pack : tag déduit du JSON (intent nommé ``greeting`` si présent,
  sinon **premier** intent du fichier) puis même tirage de variante ; puis fallback ``greeting_01.wav``
  ou ``--greeting-wav``.
- **Multi-tours** : ``--dialogue-max-turns`` boucles « VRX + STT → match → lecture WAV » sur un
  même worker Vosk (timeline continue dans les sous-titres).

Prérequis
---------
- Modèle Vosk français : ``--vosk-model-slug small-fr``, etc. (voir ``--vosk-list-models``).
- Pack WAV : ``labaudio/generate_intent_pack.py`` sur un JSON DanielCraft (ex. ``data/intents/danielcraft/outbound/*.json``) ou lab (``data/intents/lab/*.json``).

Les sous-titres reflètent la timeline cumulative Vosk sur toute la phase écoute post-ouverture.

**Défaut sonde / greeting** : ``--no-wait-full-capture-window`` est le défaut (sortie dès voix ou décroché) pour
jouer l’ouverture tôt ; sinon l’appelé reste longtemps sans audio de notre côté (souvent perçu comme « que mon
écho »). Pour une sonde complète type métriques, passer ``--wait-full-capture-window``.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
    preload_vosk_model,
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
from labcore.prospection_dialogue import (
    CallDeadline,
    ConversationSnapshot,
    DialogueContext,
    DialogueEventKind,
    IntentChain,
    build_dialogue_policy,
    infer_opening_tag_from_intent_json_paths,
    pick_opening_wav_from_pack,
)
from labcore.prospection_dialogue.audio_cache import (
    ProspectionAudioCache,
    build_prospection_audio_cache,
)
from labcore.prospection_dialogue.ports import IntentMatcherProtocol
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
        nargs="*",
        default=(),
        metavar="PATH",
        help=(
            "Un ou plusieurs JSON d’intents (ordre = priorité chaîne). "
            "Ex. : --intents-json data/stop.json data/intents/danielcraft/outbound/niveau1_ouverture.json"
        ),
    )
    p.add_argument(
        "--try-intent-reply",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Après ouverture : écoute(s) STT puis lecture WAV si un intent matche (voir --dialogue-max-turns).",
    )
    p.add_argument(
        "--dialogue-max-turns",
        type=int,
        default=1,
        help="Nombre max de tours écoute→réponse après l’ouverture (défaut 1 = comportement historique).",
    )
    p.add_argument(
        "--opening-tag",
        type=str,
        default=None,
        help=(
            "Tag JSON pour l’ouverture (ex. n1_salutation_standard) : tirage aléatoire parmi les "
            "variantes ``tag_XX.wav`` du pack. Ignoré si --greeting-wav pointe vers un fichier existant."
        ),
    )
    p.add_argument(
        "--dialogue-rng-seed",
        type=int,
        default=None,
        help="Graine RNG pour ouverture / variantes reproductibles (défaut : non déterministe).",
    )
    p.add_argument(
        "--dialogue-max-wall-sec",
        type=float,
        default=None,
        help=(
            "Budget temps **réel** max (secondes monotonic) pour toute la boucle dialogue après "
            "l’ouverture. Les écoutes STT sont tronquées si nécessaire. None ou 0 = pas de limite."
        ),
    )
    p.add_argument(
        "--terminal-intent-tags",
        type=str,
        default="n1_exit,n1_rgpd_stop_call",
        help="Tags séparés par des virgules : après lecture WAV, arrêt de la boucle dialogue.",
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
    p.add_argument(
        "--wait-full-capture-window",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Si oui et --capture-window-sec > 0 : garde VRX jusqu'à la fin de la fenêtre après la première "
            "détection (sonde complète, comme metrics_voicemail). Défaut **non** : quitte dès voix/décroché pour "
            "jouer le greeting sans long silence côté ligne."
        ),
    )
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


def _resolve_greeting_wav(
    args: argparse.Namespace,
    pack_dir: Path,
    rng: random.Random,
    *,
    intent_json_paths: tuple[Path, ...],
) -> Path | None:
    """
    Résout le WAV joué **en premier** sur la ligne (ouverture).

    Priorité :

    1. ``--greeting-wav`` si fichier existant (contrôle manuel total).
    2. ``--opening-tag`` + ``pack_dir`` : une variante ``{tag}_NN.wav`` tirée au hasard.
    3. Tag déduit des ``--intents-json`` (``greeting`` si présent, sinon premier intent du fichier) +
       ``pack_dir``.
    4. ``greeting_01.wav`` dans le pack (convention historique generate_intent_pack).
    """
    if args.greeting_wav is not None and Path(args.greeting_wav).is_file():
        return Path(args.greeting_wav)
    if args.opening_tag and pack_dir.is_dir():
        picked = pick_opening_wav_from_pack(pack_dir, str(args.opening_tag).strip(), rng)
        if picked is not None:
            return picked
    inferred = infer_opening_tag_from_intent_json_paths(intent_json_paths)
    if inferred and pack_dir.is_dir():
        picked = pick_opening_wav_from_pack(pack_dir, inferred, rng)
        if picked is not None:
            logger.info("Ouverture WAV déduite des intents : tag={} → {}", inferred, picked.name)
            return picked
    if pack_dir.is_dir():
        cand = pack_dir / "greeting_01.wav"
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

    rng = random.Random(args.dialogue_rng_seed) if args.dialogue_rng_seed is not None else random.Random()
    if args.opening_tag and not args.audio_pack_dir:
        if args.greeting_wav is None or not Path(args.greeting_wav).is_file():
            logger.error(
                "Avec --opening-tag, indiquez --audio-pack-dir (répertoire du pack WAV) "
                "ou un --greeting-wav existant pour en déduire le dossier."
            )
            return 7
    pack_hint = (
        Path(args.audio_pack_dir)
        if args.audio_pack_dir
        else (Path(args.greeting_wav).parent if args.greeting_wav else Path("."))
    )
    intent_paths_for_greeting = tuple(p for p in (args.intents_json or ()) if p is not None)
    greeting = _resolve_greeting_wav(
        args,
        pack_hint,
        rng,
        intent_json_paths=intent_paths_for_greeting,
    )
    if greeting is None:
        logger.error(
            "WAV d’ouverture introuvable : --greeting-wav, ou --audio-pack-dir avec "
            "greeting_01.wav / variantes --opening-tag, ou pack incomplet."
        )
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

    pack_dir = Path(args.audio_pack_dir) if args.audio_pack_dir else greeting.parent
    intent_paths_pre = tuple(p for p in (args.intents_json or ()) if p is not None)
    try:
        vosk_preloaded_model = preload_vosk_model(Path(model_dir))
    except Exception as e:
        logger.error("Préchargement modèle Vosk: {}", e)
        return 8
    try:
        audio_cache: ProspectionAudioCache | None = build_prospection_audio_cache(
            pack_dir=pack_dir,
            greeting_wav=greeting,
            intent_json_paths=intent_paths_pre,
        )
    except (OSError, ValueError) as e:
        logger.error("Préchargement WAV / intents: {}", e)
        return 7

    modem = build_modem(args)
    ctl = CallController(modem)

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
            "dialogue_max_turns": int(args.dialogue_max_turns),
            "opening_tag": args.opening_tag or "",
            "try_intent_reply": bool(args.try_intent_reply),
            "intent_json_paths": [str(p) for p in (args.intents_json or ())],
            "dialogue_max_wall_sec": args.dialogue_max_wall_sec,
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
            pcm_u8=audio_cache.pcm_u8_for_path(greeting),
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

        worker = VoskRealtimeWorker(
            Path(model_dir),
            sample_rate=8000,
            preloaded_model=vosk_preloaded_model,
        )
        worker.start()
        stop_reason: str | None = None
        intent_paths = intent_paths_pre
        use_dialogue = bool(args.try_intent_reply) and bool(intent_paths)
        snap = ConversationSnapshot()
        matcher: IntentMatcherProtocol | None = None
        dialogue_policy = None

        if use_dialogue:
            deadline: CallDeadline | None = None
            if args.dialogue_max_wall_sec is not None and float(args.dialogue_max_wall_sec) > 0.0:
                deadline = CallDeadline(float(args.dialogue_max_wall_sec))
            try:
                term = frozenset(
                    t.strip() for t in str(args.terminal_intent_tags or "").split(",") if t.strip()
                )
                dialogue_policy = build_dialogue_policy(
                    intent_json_paths=intent_paths,
                    pack_dir=pack_dir,
                    max_reply_turns=int(args.dialogue_max_turns),
                    terminal_tags=term,
                    rng_seed=args.dialogue_rng_seed,
                    listen_sec_per_turn=float(args.listen_sec),
                    wall_budget_sec=float(args.dialogue_max_wall_sec)
                    if args.dialogue_max_wall_sec is not None and float(args.dialogue_max_wall_sec) > 0.0
                    else None,
                )
                if audio_cache.intent_payloads:
                    matcher = IntentChain.from_payloads(
                        audio_cache.intent_payloads,
                        terminal_tags=dialogue_policy.config.terminal_intent_tags,
                    )
                else:
                    matcher = IntentChain(
                        dialogue_policy.config.intent_json_paths,
                        terminal_tags=dialogue_policy.config.terminal_intent_tags,
                    )
            except (OSError, ValueError, FileNotFoundError) as e:
                logger.error("Initialisation chaîne intents / dialogue : {}", e)
                worker.close_input()
                try:
                    worker.join_utterances(timeout=5.0)
                except Exception:
                    pass
                return 8

            dialogue_policy.event_bus.emit(
                DialogueEventKind.DIALOGUE_STARTED,
                max_turns=dialogue_policy.config.max_reply_turns,
                intent_files=[str(p) for p in dialogue_policy.config.intent_json_paths],
                wall_budget_sec=dialogue_policy.wall_budget_sec,
            )

            u_cursor = 0
            for turn in range(1, dialogue_policy.config.max_reply_turns + 1):
                ctx = DialogueContext(
                    next_turn_index=turn,
                    max_turns=dialogue_policy.config.max_reply_turns,
                    deadline=deadline,
                )
                if not dialogue_policy.continue_dialogue.is_satisfied_by(snap, ctx):
                    dialogue_policy.event_bus.emit(
                        DialogueEventKind.DIALOGUE_STOPPED,
                        reason="specification_not_satisfied",
                        turn=turn,
                        stop_dialogue=snap.stop_dialogue,
                        deadline_expired=bool(deadline and deadline.expired()),
                    )
                    break
                if turn > 1:
                    try:
                        await modem.end_outgoing_vrx_stream()
                    except Exception:
                        pass
                    opened_t = await modem.start_outgoing_vrx_stream(already_in_voice_mode=True)
                    if not opened_t:
                        logger.error("VRX indisponible avant tour STT {}", turn)
                        dialogue_policy.event_bus.emit(
                            DialogueEventKind.DIALOGUE_ERROR,
                            message="no_vrx_before_turn",
                            turn=turn,
                        )
                        break

                eff_listen = dialogue_policy.effective_listen_seconds(deadline)
                dialogue_policy.event_bus.emit(
                    DialogueEventKind.TURN_STT_START,
                    turn=turn,
                    max_turns=dialogue_policy.config.max_reply_turns,
                    listen_sec=eff_listen,
                )
                stop_reason = await pump_vrx_pcm16_to_vosk(
                    modem,
                    worker,
                    max_seconds=eff_listen,
                )
                dialogue_policy.event_bus.emit(
                    DialogueEventKind.TURN_STT_DONE,
                    turn=turn,
                    stop_reason=stop_reason or "",
                )
                if stop_reason == "remote_line_end":
                    logger.info("Tour {} STT : fin de ligne distante.", turn)
                    break

                chunk_uts = worker.snapshot_utterances()
                turn_uts = chunk_uts[u_cursor:]
                u_cursor = len(chunk_uts)
                turn_text = " ".join(u.text for u in turn_uts).strip()
                snap.last_turn_transcript = turn_text
                logger.info(
                    "Tour {}/{} STT : {}",
                    turn,
                    dialogue_policy.config.max_reply_turns,
                    turn_text[:500] or "(vide)",
                )

                outcome = matcher.match(turn_text, pack_dir, rng) if turn_text else None
                if outcome is None:
                    logger.info("Tour {} : aucun intent ne matche — fin boucle dialogue.", turn)
                    dialogue_policy.event_bus.emit(
                        DialogueEventKind.INTENT_NO_MATCH,
                        turn=turn,
                        transcript_excerpt=turn_text[:200],
                    )
                    break

                dialogue_policy.event_bus.emit(
                    DialogueEventKind.INTENT_MATCHED,
                    turn=turn,
                    tag=outcome.intent_tag,
                    variant=outcome.variant_index,
                    source_json=outcome.source_json.name,
                    terminal=outcome.terminal,
                )
                logger.info(
                    "Intent «{}» ({} v{}) pattern «{}»",
                    outcome.intent_tag,
                    outcome.source_json.name,
                    outcome.variant_index,
                    outcome.pattern_matched[:120],
                )
                dialogue_policy.event_bus.emit(
                    DialogueEventKind.WAV_REPLY_START,
                    turn=turn,
                    path=str(outcome.wav_path),
                )
                ok_r = await _play_voice_clip(
                    modem,
                    outcome.wav_path,
                    prefer_voice=True,
                    try_half_duplex=try_hd,
                    label=f"Réponse intent tour {turn}",
                    pcm_u8=audio_cache.pcm_u8_for_path(outcome.wav_path),
                )
                if not ok_r:
                    logger.warning("Lecture WAV intent échouée (tour {}).", turn)
                    dialogue_policy.event_bus.emit(
                        DialogueEventKind.DIALOGUE_ERROR,
                        message="wav_play_failed",
                        turn=turn,
                    )
                    try:
                        await modem.end_outgoing_vrx_stream()
                    except Exception:
                        pass
                    worker.close_input()
                    try:
                        worker.join_utterances(timeout=10.0)
                    except Exception:
                        pass
                    return 9
                snap.record_reply_played(outcome.intent_tag, terminal=outcome.terminal)
                await asyncio.sleep(0.15)
                if snap.stop_dialogue:
                    logger.info("Intent terminal «{}» — arrêt dialogue.", outcome.intent_tag)
                    dialogue_policy.event_bus.emit(
                        DialogueEventKind.DIALOGUE_STOPPED,
                        reason="terminal_intent",
                        tag=outcome.intent_tag,
                    )
                    break
        else:
            if bool(args.try_intent_reply) and not intent_paths:
                logger.warning("--try-intent-reply sans --intents-json : écoute STT sans réponse auto.")
            stop_reason = await pump_vrx_pcm16_to_vosk(
                modem,
                worker,
                max_seconds=max(1.0, float(args.listen_sec)),
            )

        if stop_reason == "remote_line_end" and not use_dialogue:
            logger.info("Écoute STT interrompue : fin de ligne distante.")

        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass

        worker.close_input()
        try:
            utterances = worker.join_utterances(timeout=45.0)
        except Exception as e:
            logger.exception("Vosk join: {}", e)
            utterances = []

        full_text = " ".join(u.text for u in utterances).strip()
        logger.info("Transcription cumulée (résumé): {}", full_text[:800] or "(vide)")
        if use_dialogue:
            logger.info("Memento dialogue: {}", snap.to_jsonable())

        if args.subtitle_format in ("sub", "both") and utterances and transcript_dir is not None:
            sub_path = transcript_dir / "transcript.srt"
            write_subrip(sub_path, utterances)
            logger.info("SubRip écrit: {}", sub_path)
        if args.subtitle_format in ("vtt", "both") and utterances and transcript_dir is not None:
            vtt_path = transcript_dir / "transcript.vtt"
            write_webvtt(vtt_path, utterances)
            logger.info("WebVTT écrit: {}", vtt_path)

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
