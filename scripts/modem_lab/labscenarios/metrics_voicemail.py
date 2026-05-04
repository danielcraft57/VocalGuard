#!/usr/bin/env python3
"""
Scénario sortant : sonde métriques (comme ``answer_metrics_probe``), puis répondeur.

Après composition, attend un décroché / activité voix avec le même pipeline VRX + métriques
optionnelles. Dès que la condition de déclenchement est remplie (par défaut
``voice_activity``, ce qui correspond en pratique à une prise de parole distante du type
« oui allô »), joue un WAV, émet le(s) bip(s), enregistre le message, attend le raccrochage
distant puis raccroche localement (``labcore.hangup.turbo_hangup`` dans le ``finally``).

Après fermeture du flux ``AT+VRX``, le prompt et les bips sont joués avec une **séquence voix
complète** (``prefer_already_in_voice=False`` en premier) : sans ré‑``AT+VLS=1`` / préparation,
certains Conexant envoient le ``VTX`` sans audio audible côté correspondant. Par défaut **aucune
pause** avant le prompt (pas d’attente après l’« allô ») ; en option, ``--pause-before-prompt-sec``
peut laisser finir la prise de parole distante.

Chronologie utile / confusion fréquente
---------------------------------------
1. Sonde + capture ``capture.wav`` pendant ``wait_answer_or_voice_activity``. Par défaut **7,5 s de délai**
   puis **20 s de fenêtre** (réglable) ; avec ``--capture-window-sec > 0``,
   le défaut (**``--wait-full-capture-window`` oui**) tient **toute la fenêtre** VRX (métriques + WAV alignés
   sur delay/window — comportement sonde). Pour **enchaîner le prompt dès la voix** sans attendre la fin de
   fenêtre : ``--no-wait-full-capture-window``.
2. Prompt + bips (VTX ou ``half_duplex`` uplink) — pause optionnelle via ``--pause-before-prompt-sec``.
3. **Enregistrement** du message appelé dans ``messages/msg_out_*.wav`` (bloc ``Enregistrement ligne (VRX)``).
   Le modem peut **couper l'enregistrement** si un marqueur de fin de ligne apparaît dans le flux série
   ou si DCD passe de présent à absent (voir ``stop_on_remote_hangup`` dans ``record_wav_via_serial``).
4. Sans voix après **delay + fenêtre** (sauf ``--extend-wait-beyond-capture``) : timeout phase sonde → pas de
   prompt, raccrochage dans le ``finally``.
5. Option ``--wait-remote-hangup-sec`` : **seulement écoute**, pas d'enregistrement ; sur USB sortant
   ``DCD`` est souvent toujours faux → logs espacés et ``timeout`` normal.

Les helpers bips / normalisation WAV sont réutilisés depuis ``answering_machine``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

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
from labcore.call_control import CallController
from labcore.call_watch import wait_remote_line_end_optional
from labcore.hangup import turbo_hangup
from labcore.voice_line import (
    play_wav_line_fallback,
    play_wav_via_half_duplex_uplink,
    record_wav_line_fallback,
)
from labscenarios.answering_machine import _enforce_wav_duration, _generate_beep_u8, _write_u8_wav

# Au-dessous de ce seuil, la pause avant prompt est ignorée (0 et ~1 ms pratiques).
_PROMPT_PAUSE_EPS_SEC = 1e-3


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sonde métrique sortante puis message WAV + mode répondeur (bip + enregistrement + attente raccrochage)."
    )
    add_modem_args(p, need_number=True)
    p.add_argument(
        "--prompt-wav",
        type=Path,
        required=True,
        help="WAV à jouer après détection de la voix distante (ex. consigne avant le bip).",
    )
    p.add_argument(
        "--play-after-reason",
        choices=("voice_activity", "any_ready"),
        default="voice_activity",
        help=(
            "voice_activity: parole VAD ou signal modem de décroché (DCD/DLE). "
            "any_ready: tout déclencheur sonde (secours)."
        ),
    )
    p.add_argument(
        "--wait-answer-or-voice-sec",
        type=float,
        default=45.0,
        help=(
            "Timeout VRX si --capture-window-sec est 0. Avec une fenêtre > 0 (défaut), l'attente est "
            "surtout limitée à delay+fenêtre sauf --extend-wait-beyond-capture."
        ),
    )
    p.add_argument(
        "--post-answer-observe-sec",
        type=float,
        default=0.0,
        help=(
            "Après détection, prolonge VRX pour métriques (ignoré si --capture-window-sec > 0). "
            "Défaut 0 pour enchaîner vite le prompt répondeur."
        ),
    )
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
    p.add_argument(
        "--dated-outfiles",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Sous-dossier horodaté generated/metrics_voicemail/<ts>/ (metrics + capture + rapport).",
    )
    p.add_argument("--metrics-thread", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--metrics-flush-sec", type=float, default=0.5)
    p.add_argument("--record-wav-from-start", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--record-wav-mode", choices=("inline", "thread"), default="inline")
    p.add_argument(
        "--record-wav-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/metrics_voicemail/capture.wav"),
    )
    p.add_argument("--record-wav-sec", type=float, default=-1.0)
    p.add_argument(
        "--metrics-out",
        type=Path,
        default=Path("scripts/modem_lab/generated/metrics_voicemail/metrics.csv"),
    )
    p.add_argument(
        "--capture-delay-sec",
        type=float,
        default=7.5,
        help="Début collecte métriques/WAV après ouverture VRX (défaut 7,5 s — laisse passer sonnerie avant sonde).",
    )
    p.add_argument(
        "--capture-window-sec",
        type=float,
        default=20.0,
        help="Durée max de collecte après le délai (défaut 20 s ; 0 = jusqu'à timeout VRX).",
    )
    p.add_argument(
        "--wait-full-capture-window",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Si oui (défaut) et --capture-window-sec > 0 : garde VRX jusqu'à la fin de la fenêtre après "
            "la première détection — **sonde complète** (métriques + capture.wav sur tout le delay+window). "
            "``--no-wait-full-capture-window`` : quitte dès voix/décroché pour jouer le prompt plus tôt "
            "(tronque la sonde)."
        ),
    )
    p.add_argument(
        "--extend-wait-beyond-capture",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Si oui : après (delay + fenêtre), continue d'écouter la voix jusqu'à --wait-answer-or-voice-sec. "
            "Défaut non : **sans voix** après la fenêtre de sonde → timeout puis raccrochage (pas de prompt)."
        ),
    )
    p.add_argument("--auto-report", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--report-frame-ms", type=float, default=80.0)
    p.add_argument("--report-hop-ms", type=float, default=40.0)
    p.add_argument("--record-seconds", type=float, default=25.0, help="Durée enregistrement message laissé par l'appelé.")
    p.add_argument(
        "--record-timeout-extra-sec",
        type=float,
        default=5.0,
        help="Marge timeout au-delà de --record-seconds.",
    )
    p.add_argument(
        "--record-dir",
        type=Path,
        default=Path("scripts/modem_lab/generated/metrics_voicemail/messages"),
        help="Dossier des messages enregistrés.",
    )
    p.add_argument("--beep", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--beep-ms", type=int, default=300)
    p.add_argument("--beep-hz", type=int, default=1000)
    p.add_argument("--beep-pattern", choices=("single", "double"), default="double")
    p.add_argument("--beep2-ms", type=int, default=150)
    p.add_argument("--beep2-hz", type=int, default=780)
    p.add_argument(
        "--wait-remote-hangup-sec",
        type=float,
        default=45.0,
        help=(
            "Après enregistrement : écoute VRX pour marqueur de fin (pas de nouvel enregistrement). "
            "USB sortant : DCD souvent absent → timeout normal ; 0 = sauter."
        ),
    )
    p.add_argument(
        "--remote-hangup-dcd-log-sec",
        type=float,
        default=18.0,
        help="Intervalle min entre deux logs DCD pendant wait_remote_hangup (réduit le spam).",
    )
    p.add_argument(
        "--pause-before-prompt-sec",
        type=float,
        default=0.0,
        help=(
            "Pause après fermeture VRX avant lecture du prompt. Défaut 0 (enchaîne sans attendre la fin de l'« allô »). "
            f"Valeur ≤ {_PROMPT_PAUSE_EPS_SEC:g} s : aucune pause ; ex. 0,85 s pour laisser parler le correspondant."
        ),
    )
    p.add_argument(
        "--prompt-play-prefer-already-voice",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Si oui: tente VTX sans renvoyer FCLASS/VLS (ancien comportement). Défaut: non — mieux entendu après VRX.",
    )
    p.add_argument(
        "--half-duplex-uplink-for-prompt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Si oui (défaut): après la sonde VRX, envoie prompt/bips via half_duplex_send_uplink_u8 "
            "(ferme VRX, VTX, rouvre VRX) — souvent audible là où VTX seul reste muet."
        ),
    )
    return p.parse_args()


def _play_trigger_ok(why: str, mode: str) -> bool:
    if mode == "any_ready":
        return True
    # voice_activity : parole distante ou indices série de décroché (DCD/DLE).
    return why in ("voice_activity", "answer_tone")


async def _play_voice_clip(
    modem,
    wav_path: Path,
    *,
    prefer_voice: bool,
    try_half_duplex: bool,
    label: str,
) -> bool:
    if try_half_duplex and await play_wav_via_half_duplex_uplink(modem, wav_path):
        logger.info("{} via half_duplex uplink", label)
        return True
    if try_half_duplex:
        logger.info("{} — half_duplex indisponible ou KO, fallback VTX classique", label)
    return await play_wav_line_fallback(modem, wav_path, prefer_already_in_voice=prefer_voice)


async def run() -> int:
    """
    Codes: 0 OK, 1 init, 2 prep voix, 3 dial, 4 config capture, 5 attente sans décroché,
    6 mauvais type de détection, 7 lecture prompt, 8 enregistrement.
    """
    args = parse_args()
    prompt_wav = Path(args.prompt_wav)
    if not prompt_wav.is_file():
        logger.error("WAV prompt introuvable: {}", prompt_wav)
        return 7

    if bool(args.dated_outfiles):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        capture_dir = Path("scripts/modem_lab/generated/metrics_voicemail") / ts
        capture_dir.mkdir(parents=True, exist_ok=True)
        args.metrics_out = capture_dir / "metrics.csv"
        args.record_wav_out = capture_dir / "capture.wav"
        args.record_dir = capture_dir / "messages"
        args.record_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Dossier session: {}", capture_dir)

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
            voice_wait_caps_at_capture_span=not bool(args.extend_wait_beyond_capture),
        )
        report_session_extra: dict[str, Any] = {
            "scenario": "metrics_voicemail",
            "wait_full_capture_window": bool(args.wait_full_capture_window),
            "extend_wait_beyond_capture": bool(args.extend_wait_beyond_capture),
        }
        if float(args.capture_window_sec) > 0.0 and not bool(args.extend_wait_beyond_capture):
            report_session_extra["voice_wait_seconds_cap"] = round(
                float(args.capture_delay_sec) + float(args.capture_window_sec), 3
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
                exit_wait_on_voice=not bool(args.wait_full_capture_window),
                report_session_extra=report_session_extra,
            )
        except AnswerWaitConfigError as e:
            logger.error("{}", e)
            return 4

        logger.info("Attente décroché/voix -> ready={} reason={}", ready, why)
        if not ready:
            logger.error("Pas de détection avant timeout — pas de lecture prompt")
            return 5
        if not _play_trigger_ok(why, str(args.play_after_reason)):
            logger.error(
                "Détection reason={} incompatible avec --play-after-reason={} (ex.: utiliser any_ready ou ajuster VAD)",
                why,
                args.play_after_reason,
            )
            return 6

        pause_prompt = max(0.0, float(args.pause_before_prompt_sec))
        if pause_prompt > _PROMPT_PAUSE_EPS_SEC:
            logger.info("Pause {:.4f}s avant prompt (après fermeture VRX)", pause_prompt)
            await asyncio.sleep(pause_prompt)

        prefer_voice = bool(args.prompt_play_prefer_already_voice)
        try_hd = bool(args.half_duplex_uplink_for_prompt)
        logger.info(
            "Lecture prompt après voix distante: {} (prefer_already_in_voice={}, half_duplex={})",
            prompt_wav,
            prefer_voice,
            try_hd,
        )
        played = await _play_voice_clip(
            modem,
            prompt_wav,
            prefer_voice=prefer_voice,
            try_half_duplex=try_hd,
            label="Prompt",
        )
        if not played:
            logger.error("Echec lecture prompt")
            return 7
        await asyncio.sleep(0.2)

        if bool(args.beep):
            logger.info(
                "Bip enregistrement (pattern={}, {}ms@{}Hz / {}ms@{}Hz)",
                args.beep_pattern,
                args.beep_ms,
                args.beep_hz,
                args.beep2_ms,
                args.beep2_hz,
            )
            with tempfile.NamedTemporaryFile(prefix="metrics_vm_beep_", suffix=".wav", delete=False) as tmp:
                beep_path = Path(tmp.name)
            try:
                beep = _generate_beep_u8(max(60, int(args.beep_ms)), max(200, int(args.beep_hz)))
                if args.beep_pattern == "double":
                    beep += bytes([128]) * int(8000 * 0.08)
                    beep += _generate_beep_u8(max(60, int(args.beep2_ms)), max(200, int(args.beep2_hz)))
                beep += bytes([128]) * int(8000 * 0.1)
                _write_u8_wav(beep_path, beep, rate=8000)
                ok_beep = await _play_voice_clip(
                    modem,
                    beep_path,
                    prefer_voice=prefer_voice,
                    try_half_duplex=try_hd,
                    label="Bip",
                )
                if not ok_beep:
                    logger.warning("Bip non joué correctement")
            finally:
                try:
                    beep_path.unlink(missing_ok=True)
                except Exception:
                    pass

        try:
            await modem.end_outgoing_vrx_stream()
        except Exception:
            pass

        rec_dir = Path(args.record_dir)
        rec_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rec_path = rec_dir / f"msg_out_{stamp}.wav"
        rec_seconds = max(1.0, float(args.record_seconds))
        timeout_sec = rec_seconds + max(1.0, float(args.record_timeout_extra_sec))
        logger.info(
            "Enregistrement message (VRX dédié, {:.1f}s max) -> {}",
            rec_seconds,
            rec_path,
        )
        try:
            recorded = await asyncio.wait_for(
                record_wav_line_fallback(
                    modem,
                    rec_seconds,
                    rec_path,
                    prefer_already_in_voice=True,
                    stop_on_remote_hangup=True,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.error("Timeout enregistrement après {:.1f}s", timeout_sec)
            recorded = False
        if not recorded:
            logger.error("Enregistrement message échoué")
            return 8
        _enforce_wav_duration(rec_path, rec_seconds)
        logger.info("Message enregistré: {}", rec_path)

        hup, hwhy = await wait_remote_line_end_optional(
            modem,
            timeout_sec=float(args.wait_remote_hangup_sec),
            already_in_voice_mode=True,
            dcd_log_heartbeat_sec=float(args.remote_hangup_dcd_log_sec),
            session_note="(le WAV message est déjà écrit).",
        )
        if hup is not None:
            logger.info("Attente raccrochage distant -> detected={} reason={}", hup, hwhy)

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
    setup_logging("metrics_voicemail")
    raise SystemExit(asyncio.run(run()))
