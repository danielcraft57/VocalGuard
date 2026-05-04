#!/usr/bin/env python3
"""
Appel sortant **sans message audio** : après composition et attentes (tonalité décroché / budget sonneries),
ouvre **AT+VRX** et affiche les événements **« ça parle »** (VAD) — pour mesurer latence / présence de voix.

Pas de ``AT+VTX``, pas de fichier WAV.

Usage principal:
- vérifier qu'on reçoit bien l'audio de ligne en mode voice-blind
- mesurer latence de détection parole et comportement hangup distant
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

# Permet d'executer ce script directement depuis la racine du depot.
_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.hangup import turbo_hangup
from labcore.ring_timing import ringback_wait_sec
from labcore.voice_activity import SpeechActivityDetector, VaKind
from labcore.vrx_vad_pump import pump_vrx_speech_events


def parse_args() -> argparse.Namespace:
    """Arguments CLI du scénario d'écoute VAD sortante."""
    p = argparse.ArgumentParser(
        description="Appel sortant sans annonce : ecoute ligne + detection parole (VAD / logs latence)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_modem_args(p, need_number=True)
    p.add_argument(
        "--listen-sec",
        type=float,
        default=90.0,
        help="Duree max d'ecoute VRX + VAD apres etablissement appel (s)",
    )
    p.add_argument("--vad-threshold", type=float, default=18.0, help="Seuil MAD (comme modem_handler experimental)")
    p.add_argument("--vad-min-speech-ms", type=float, default=120.0, help="Duree min au-dessus du seuil = parole")
    p.add_argument("--vad-hangover-ms", type=float, default=400.0, help="Silence pour fin de parole")
    p.add_argument(
        "--stop-after-speech-start",
        action="store_true",
        help="Arreter l'ecoute des la premiere detection « ca parle » (sinon ecoute jusqu'a --listen-sec)",
    )
    p.add_argument("--quiet-hangup-tty", action="store_true", help="Pas de bips console au hangup turbo")
    p.add_argument(
        "--wait-remote-answer",
        action="store_true",
        help="CONNECT/VCON avant fin dial (incompatible avec --voice-blind-dial)",
    )
    p.add_argument(
        "--voice-blind-dial",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Composition ATDT…; OK rapide (defaut: oui)",
    )
    p.add_argument(
        "--wait-answer-tone",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Attendre DLE+a / CONNECT sur le port serie apres dial (defaut: oui)",
    )
    p.add_argument("--answer-tone-timeout-sec", type=float, default=45.0)
    p.add_argument("--answer-tone-silent-bail-sec", type=float, default=12.0)
    p.add_argument("--post-dial-wait-sec", type=float, default=12.0)
    p.add_argument("--tone-fail-wait-mode", choices=("rings", "post-dial"), default="rings")
    p.add_argument("--dial-timeout-sec", type=float, default=25.0)
    p.add_argument("--wait-rings", type=int, default=0)
    p.add_argument("--ring-duration-sec", type=float, default=5.0)
    p.add_argument("--no-prepare-voice-line", action="store_true")
    p.add_argument("--post-offhook-delay-sec", type=float, default=2.0)
    p.add_argument("--no-print-vad", action="store_true", help="Desactive print stdout (garde loguru)")
    p.add_argument("--no-log-vad", action="store_true", help="Desactive log fichier/console loguru pour VAD")
    p.add_argument(
        "--no-stop-on-remote-hangup",
        action="store_true",
        help="Ne pas couper l'ecoute VAD quand le modem signale fin de ligne (NO CARRIER, etc. sur le flux VRX)",
    )
    return p.parse_args()


async def run() -> int:
    """
    Exécute l'appel sortant d'écoute VAD.

    Codes de retour:
    - 0: succès / interruption volontaire
    - 1: configuration/preparation invalide ou init KO
    - 2: composition non confirmée
    - 3: ouverture VRX impossible
    """
    args = parse_args()
    modem = None
    hangup_done = False
    exit_code = 0
    # prepare: applique la préparation voix avant composition.
    prepare = not bool(args.no_prepare_voice_line)
    # voice_blind: force ATDT...; (retour immédiat sans CONNECT explicite).
    voice_blind = bool(args.voice_blind_dial)

    if voice_blind and args.wait_remote_answer:
        logger.error("--voice-blind-dial est incompatible avec --wait-remote-answer")
        return 1
    if voice_blind and not prepare:
        logger.error("--voice-blind-dial requiert la preparation voix (ne pas passer --no-prepare-voice-line)")
        return 1

    try:
        modem = build_modem(args)
        logger.info("Initialisation modem...")
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1

        if args.wait_remote_answer and not prepare:
            logger.warning(
                "--wait-remote-answer sans preparation voix : risque class 0 / pas de porteuse voix."
            )

        prefer_media = prepare
        if prepare and (args.wait_remote_answer or voice_blind):
            if args.wait_remote_answer:
                logger.info("Mode attente CONNECT/VCON (codec avant dial, sans +VLS=1).")
            else:
                logger.info("Voice-blind-dial : codec avant ATDT avec « ; ».")
            if not await modem.enter_voice_codec_before_dial():
                logger.error("Echec preparation voix avant composition")
                return 1
        elif prepare:
            logger.info("Preparation voix (+FCLASS=8 / +VLS=1) avant composition.")
            if not await modem.enter_voice_line_for_outbound_dial():
                logger.error("Echec preparation voix (+VLS=1)")
                return 1
            off_d = max(0.0, float(args.post_offhook_delay_sec))
            if off_d:
                await asyncio.sleep(off_d)

        logger.info("Composition du numero {}", args.number)
        dial_timeout = max(5.0, float(args.dial_timeout_sec))
        if args.wait_remote_answer:
            dial_timeout = max(dial_timeout, 120.0)
        blind_dial = voice_blind or (not args.wait_remote_answer)
        ok, raw = await modem.dial_number(args.number, timeout=dial_timeout, blind=blind_dial)
        logger.info("Dial {} -> ok={} raw={}", args.number, ok, raw or "(vide)")
        if not ok:
            logger.error("Composition / etablissement non confirmes ({})", raw or "sans detail")
            return 2

        if args.wait_remote_answer and int(args.wait_rings) > 0:
            logger.warning("--wait-rings ignore avec --wait-remote-answer")

        elif voice_blind or not args.wait_remote_answer:
            ring_wait = ringback_wait_sec(int(args.wait_rings), float(args.ring_duration_sec))
            if ring_wait <= 0 and voice_blind:
                ring_wait = max(0.0, float(args.post_dial_wait_sec))
            ring_budget_before_serial = ring_wait

            used_audio_cue = False
            got_cue = False
            elapsed_tone = 0.0
            uart_aucun_octet = False
            if args.wait_answer_tone:
                bail = float(args.answer_tone_silent_bail_sec)
                ring_cap = ringback_wait_sec(int(args.wait_rings), float(args.ring_duration_sec))
                if bail > 0 and args.tone_fail_wait_mode == "rings" and ring_cap > 0:
                    capped = min(bail, ring_cap)
                    if capped < bail:
                        logger.info(
                            "answer-tone-silent-bail-sec plafonne a {:.1f} s (budget sonneries)",
                            capped,
                        )
                    bail = capped
                got_cue, elapsed_tone, uart_aucun_octet = await modem.wait_voice_outbound_answer(
                    max(5.0, float(args.answer_tone_timeout_sec)),
                    silent_bail_sec=bail,
                )
                used_audio_cue = True

            if used_audio_cue:
                fail_label = "Pas d'evenement decroche sur le port (DLE+a / CONNECT / VCON)"
                if got_cue:
                    ring_wait = 0.0
                elif args.tone_fail_wait_mode == "post-dial":
                    ring_wait = max(0.0, float(args.post_dial_wait_sec))
                    logger.info("{} — repli {:.1f} s (post-dial)", fail_label, ring_wait)
                elif uart_aucun_octet:
                    ring_wait = 0.0
                    logger.info("{} — serie muette {:.1f} s", fail_label, elapsed_tone)
                else:
                    ring_wait = max(0.0, ring_budget_before_serial - elapsed_tone)
                    logger.info(
                        "{} — pause complementaire {:.1f} s (rings)",
                        fail_label,
                        ring_wait,
                    )
            if ring_wait > 0:
                logger.info("Pause avant ecoute VAD : {:.1f} s", ring_wait)
                await asyncio.sleep(ring_wait)

        logger.info(
            "Pas de WAV — ouverture ecoute VRX + VAD ({:.0f} s max, seuil MAD {:.1f}).",
            float(args.listen_sec),
            float(args.vad_threshold),
        )
        print(
            "\n>>> Parlez au combine distant ; les lignes [VAD] indiquent parole detectee.\n",
            flush=True,
        )

        opened = await modem.start_outgoing_vrx_stream(already_in_voice_mode=prefer_media)
        if not opened:
            logger.error("AT+VRX (CONNECT) impossible — ecoute abandonnee, raccrochage")
            ok_hang, cycles = await turbo_hangup(
                modem,
                enable_console_beep=not args.quiet_hangup_tty,
                cmd_timeout=0.2,
            )
            hangup_done = True
            logger.info("Raccrochage -> ok={} cycles={}", ok_hang, cycles)
            return 3

        stop_ev = asyncio.Event()
        speech_seen = asyncio.Event()

        async def on_ev(ev):
            if ev.kind == VaKind.SPEECH_START:
                speech_seen.set()
            if args.stop_after_speech_start and ev.kind == VaKind.SPEECH_START:
                stop_ev.set()

        det = SpeechActivityDetector(
            threshold=float(args.vad_threshold),
            min_speech_ms=float(args.vad_min_speech_ms),
            hangover_ms=float(args.vad_hangover_ms),
        )

        _n_ev, stop_reason = await pump_vrx_speech_events(
            modem,
            on_ev,
            detector=det,
            stop_event=stop_ev,
            max_seconds=float(args.listen_sec),
            session_label="ECOUTE-VAD",
            log_latencies=not args.no_log_vad,
            print_events=not args.no_print_vad,
            stop_on_remote_hangup=not args.no_stop_on_remote_hangup,
        )

        await modem.end_outgoing_vrx_stream()

        if stop_reason == "remote_line_end":
            logger.info("Ecoute arretee : detection fin de ligne / raccrochage distant (flux modem).")
            print("[Resume] Fin de ligne detectee sur le flux serie — ecoute coupee.", flush=True)

        if speech_seen.is_set():
            logger.info("Resume : au moins une activite vocale detectee sur la ligne.")
            print("[Resume] Parole / bruit fort detecte au moins une fois.", flush=True)
        else:
            logger.warning("Resume : aucune parole au-dessus du seuil dans la fenetre d'ecoute.")
            print("[Resume] Pas de parole detectee (seuil ou ligne muette).", flush=True)

        ok_hang, cycles = await turbo_hangup(
            modem,
            enable_console_beep=not args.quiet_hangup_tty,
            cmd_timeout=0.2,
        )
        hangup_done = True
        logger.info("Raccrochage -> ok={} cycles={}", ok_hang, cycles)
        print(f"[Hangup] cycles={cycles} succes={ok_hang}")

        return exit_code
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        try:
            if modem is not None:
                await modem.end_outgoing_vrx_stream()
        except Exception:
            pass
        return 0
    finally:
        if modem is not None and not hangup_done:
            try:
                await asyncio.shield(
                    turbo_hangup(
                        modem,
                        enable_console_beep=not args.quiet_hangup_tty,
                        cmd_timeout=0.2,
                    )
                )
                hangup_done = True
            except BaseException:
                pass
        if modem is not None:
            try:
                modem.close()
            except Exception:
                pass


if __name__ == "__main__":
    setup_logging("outbound_listen_vad")
    raise SystemExit(asyncio.run(run()))
