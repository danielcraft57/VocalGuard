#!/usr/bin/env python3
"""
Appel sortant : composition, message WAV sur la ligne, option enregistrement type répondeur, hangup turbo.

- Composition aveugle : +FCLASS=8, +VLS=1 puis ATDT…; (guide USR 5637).
- Attente décroché (--wait-remote-answer) : +FCLASS=8 + codec sans +VLS=1, puis ATDT sans « ; ».
  En class 0 seul, le modem attend une porteuse données : vers un mobile en voix, pas de CONNECT → timeout / BUSY.
- Attente sonneries **estimée (temps)** : `--wait-rings N` × `--ring-duration-sec` (ex. N=3 et 5 s → ~15 s ; N=50 et 4,5 s → ~225 s).
  Ce n’est pas le comptage DLE+R sur le fil ; les indications série sont dans les logs modem.
- Si pas de CONNECT/VCON (ex. mobile) : **--voice-blind-dial** puis **--wait-answer-tone** (DLE+a, CONNECT/VCON, code 1
  sur le port serie — voir `backend.core.telephony_events`). Repli **--post-dial-wait-sec** et **--tone-fail-wait-mode**.
  **--answer-tone-silent-bail-sec** limite l'attente si le modem reste muet en serie.

Le WAV annonce doit idéalement être 8 kHz mono 8-bit (pack modem_lab generated/.../modem_wav).
Il est chargé en mémoire après init modem (échec immédiat si invalide ; pas d’I/O disque au moment AT+VTX).

Exemples de commandes à lancer : voir la fin de ``python scripts/modem_lab/labscenarios/outbound_announce.py --help``.
"""

import argparse
import asyncio
import tempfile
import wave
from datetime import datetime
from pathlib import Path

from loguru import logger

from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from backend.core.modem_handler import wav_file_to_u8_pcm_for_modem
from labcore.hangup import turbo_hangup
from labcore.voice_line import play_wav_line_fallback, record_wav_line_fallback
from labscenarios.answering_machine import _enforce_wav_duration, _generate_beep_u8, _write_u8_wav


def compute_ringback_wait_sec(wait_rings: int, ring_duration_sec: float) -> float:
    """Duree d'attente approximative pour simuler N cycles sonnerie / silence (ligne fixe / mobile)."""
    n = max(0, int(wait_rings))
    period = max(0.0, float(ring_duration_sec))
    return float(n * period)


_OUTBOUND_TEST_EXAMPLES = r"""
Exemples a tester (PowerShell, depuis la racine du depot VocalGuard ; adapter COM*, numero, chemin WAV) :

  [A] Voice-blind + ecoute serie + budget sonneries (logs : budget / ecoute serie / pause complementaire) :
       python scripts/modem_lab/labscenarios/outbound_announce.py --port COM6 --number "+33999888777" `
         --message-wav ".\chemin\vers\annonce_8k_mono.wav" --voice-blind-dial `
         --wait-answer-tone --wait-rings 2 --ring-duration-sec 5 `
         --tone-fail-wait-mode rings

  [B] Meme chose sans double attente implicite : desactive le bail silence serie (ecoute jusqu'au timeout AT) :
       python scripts/modem_lab/labscenarios/outbound_announce.py --port COM6 --number "+33999888777" `
         --message-wav ".\chemin\vers\annonce_8k_mono.wav" --voice-blind-dial `
         --wait-answer-tone --answer-tone-silent-bail-sec 0 `
         --wait-rings 2 --ring-duration-sec 5 --tone-fail-wait-mode rings

  [C] Sans --wait-answer-tone : delai fixe estime (N x duree cycle) avant le WAV :
       python scripts/modem_lab/labscenarios/outbound_announce.py --port COM6 --number "+33999888777" `
         --message-wav ".\chemin\vers\annonce_8k_mono.wav" --voice-blind-dial `
         --wait-rings 3 --ring-duration-sec 5
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Appel sortant : annonce WAV, option enregistrement repondeur, raccrochage turbo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_OUTBOUND_TEST_EXAMPLES,
    )
    add_modem_args(parser, need_number=True)
    parser.add_argument(
        "--message-wav",
        required=True,
        help="Fichier WAV a jouer sur la ligne (8 kHz mono recommande)",
    )
    parser.add_argument(
        "--pre-play-delay-sec",
        type=float,
        default=0.2,
        help="Pause apres dial reussi avant lecture du message (s)",
    )
    parser.add_argument(
        "--post-play-pause-sec",
        type=float,
        default=0.35,
        help="Pause apres fin du message avant enregistrement ou raccrochage (s)",
    )
    parser.add_argument(
        "--quiet-hangup-tty",
        action="store_true",
        help="Desactive les bips console pendant le hangup turbo",
    )
    parser.add_argument(
        "--wait-remote-answer",
        action="store_true",
        help=(
            "Attendre CONNECT ou VCON (ATDT sans ';'). Exige le mode voix avant le numero (+FCLASS=8 + codec, "
            "sans +VLS=1) : sinon class 0 attend une porteuse donnees introuvable sur un appel vocal. "
            "Timeout mini 120 s. Incompatible avec --voice-blind-dial."
        ),
    )
    parser.add_argument(
        "--voice-blind-dial",
        action="store_true",
        help=(
            "Apres +FCLASS=8 + codec (sans +VLS=1), composer ATDT…; : OK rapide sans CONNECT. "
            "Puis --wait-answer-tone (recommande) ou attente --wait-rings / --post-dial-wait-sec avant le WAV."
        ),
    )
    parser.add_argument(
        "--wait-answer-tone",
        action="store_true",
        help=(
            "Apres composition aveugle OK, lire le port serie jusqu'a signe de decroche : DLE+a (USR 5637), "
            "CONNECT ou VCON. Sinon repli sur --post-dial-wait-sec ou --wait-rings (selon le cas)."
        ),
    )
    parser.add_argument(
        "--answer-tone-timeout-sec",
        type=float,
        default=45.0,
        help="Delai max pour --wait-answer-tone si le port reste actif ou muet jusqu'a la fin (s)",
    )
    parser.add_argument(
        "--answer-tone-silent-bail-sec",
        type=float,
        default=12.0,
        help=(
            "Si > 0 : abandon de --wait-answer-tone apres autant de secondes sans aucun octet en lecture serie "
            "(0 = desactive, attendre tout le --answer-tone-timeout-sec ; utile quand le modem ne signale pas la sonnerie). "
            "Avec --tone-fail-wait-mode rings et --wait-rings > 0, la valeur est plafonnee au budget "
            "wait-rings x ring-duration-sec pour ne pas faire sonner la ligne plus longtemps que ce budget."
        ),
    )
    parser.add_argument(
        "--post-dial-wait-sec",
        type=float,
        default=12.0,
        help="Apres dial aveugle : attente de repli si pas de --wait-answer-tone ou pas d'evenement detecte",
    )
    parser.add_argument(
        "--tone-fail-wait-mode",
        choices=("rings", "post-dial"),
        default="rings",
        help=(
            "Si --wait-answer-tone sans succes : "
            "'rings' = garder --wait-rings x --ring-duration-sec ; "
            "'post-dial' = n'attendre que --post-dial-wait-sec"
        ),
    )
    parser.add_argument(
        "--dial-timeout-sec",
        type=float,
        default=25.0,
        help="Timeout modem pour la composition (ou l'attente decroche si --wait-remote-answer)",
    )
    parser.add_argument(
        "--wait-rings",
        type=int,
        default=0,
        help=(
            "Nombre de cycles sonnerie estimes avant le WAV (entier >= 0). "
            "Duree totale ~ --wait-rings x --ring-duration-sec (ex. 3 et 5 s -> ~15 s ; 50 et 4.5 s -> ~225 s). "
            "Sert surtout au repli si --wait-answer-tone ne voit pas DLE+a / CONNECT (--tone-fail-wait-mode rings)."
        ),
    )
    parser.add_argument(
        "--ring-duration-sec",
        type=float,
        default=5.0,
        help=(
            "Secondes par cycle sonnerie+silence (FR souvent 4,5–6). Multiplie par --wait-rings pour le delai cumule."
        ),
    )
    parser.add_argument(
        "--no-prepare-voice-line",
        action="store_true",
        help=(
            "Sans preparation voix : mode aveugle sans +FCLASS=8 / +VLS=1 ; avec --wait-remote-answer, ATDT "
            "reste en class 0 (deconseille pour appel vocal vers mobile)."
        ),
    )
    parser.add_argument(
        "--post-offhook-delay-sec",
        type=float,
        default=2.0,
        help="Pause apres +VLS=1 avant composition (laisser la tonalite / S6)",
    )
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=0.0,
        help="Apres le message : enregistrer la ligne pendant N secondes (0 = pas d'enregistrement)",
    )
    parser.add_argument(
        "--record-dir",
        default=str(Path(__file__).resolve().parents[1] / "generated" / "voicemail_outbound"),
        help="Dossier des fichiers enregistres si --record-seconds > 0",
    )
    parser.add_argument(
        "--beep-before-record",
        action="store_true",
        help="Emettre un bip court avant l'enregistrement (comme un repondeur)",
    )
    parser.add_argument("--beep-ms", type=int, default=300, help="Duree du bip (ms)")
    parser.add_argument("--beep-hz", type=int, default=1000, help="Frequence du bip (Hz)")
    parser.add_argument(
        "--record-timeout-extra-sec",
        type=float,
        default=5.0,
        help="Marge timeout asyncio au-dela de record-seconds",
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    wav = Path(args.message_wav)
    logger.debug("Args outbound_announce: {}", args)

    modem = None
    hangup_done = False
    exit_code = 0
    prepare = not bool(args.no_prepare_voice_line)
    voice_blind = bool(args.voice_blind_dial)
    # +VLS=1 (aveugle) ou codec avant dial (wait / voice-blind) : contexte voix pour VTX/VRX.
    prefer_media = prepare

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

        if not wav.is_file():
            logger.error("Message WAV introuvable: {}", wav)
            return 1
        try:
            pcm_message, pcm_message_rate = wav_file_to_u8_pcm_for_modem(wav)
        except (ValueError, OSError, wave.Error) as e:
            logger.error("Message WAV invalide ou illisible: {}", e)
            return 1
        logger.info(
            "Annonce prechargee: {} octets PCM, {:.0f} Hz — pas de lecture disque au moment du VTX",
            len(pcm_message),
            pcm_message_rate,
        )
        if pcm_message_rate != 8000:
            logger.warning(
                "Frequence annonce {:.0f} Hz ; 8000 Hz mono est ideal pour la ligne",
                pcm_message_rate,
            )

        if args.wait_remote_answer and not prepare:
            logger.warning(
                "--wait-remote-answer sans preparation voix : ATDT en class 0 attend une porteuse donnees — "
                "souvent BUSY / echec vers un mobile en voix. Retirer --no-prepare-voice-line."
            )

        if prepare and (args.wait_remote_answer or voice_blind):
            if args.wait_remote_answer:
                logger.info(
                    "Attente decroche : mode voix (+FCLASS=8, codec, sans +VLS=1) puis ATDT sans « ; » "
                    "(CONNECT / VCON pour liaison vocale, pas porteuse donnees class 0)."
                )
            else:
                logger.info(
                    "Voice-blind-dial : +FCLASS=8 + codec puis ATDT avec « ; » — pas de CONNECT requis ; "
                    "ajuster --post-dial-wait-sec ou --wait-rings pour le moment du message."
                )
            if not await modem.enter_voice_codec_before_dial():
                logger.error("Echec preparation voix (FCLASS / VSD / VSM) avant composition")
                return 1
        elif prepare:
            logger.info("Preparation ligne voix avant composition aveugle (+VLS=1, tonalite)...")
            if not await modem.enter_voice_line_for_outbound_dial():
                logger.error("Echec preparation voix (+FCLASS=8 / +VLS=1)")
                return 1
            off_d = max(0.0, float(args.post_offhook_delay_sec))
            if off_d:
                logger.debug("Pause post-décrochage +VLS=1 {:.2f}s", off_d)
                await asyncio.sleep(off_d)

        logger.info("Composition du numero {}", args.number)
        dial_timeout = max(5.0, float(args.dial_timeout_sec))
        if args.wait_remote_answer:
            dial_timeout = max(dial_timeout, 120.0)
        blind_dial = voice_blind or (not args.wait_remote_answer)
        ok, raw = await modem.dial_number(
            args.number,
            timeout=dial_timeout,
            blind=blind_dial,
        )
        logger.info("Dial {} -> ok={} raw={}", args.number, ok, raw or "(vide)")
        if not ok:
            if args.wait_remote_answer and raw and "BUSY" in raw.upper():
                logger.info(
                    "Reponse BUSY : delai modem (ATS7), ligne occupee, ou contexte encore en class 0 sans prep voix. "
                    "Defaut MODEM_S7=120 ; decrocher tot ; verifier que la prep FCLASS=8 + codec a reussi (logs init)."
                )
            logger.error("Composition / etablissement appel non confirmes ({})", raw or "sans detail")
            return 2

        if args.wait_remote_answer and int(args.wait_rings) > 0:
            logger.warning(
                "--wait-rings est ignore avec --wait-remote-answer (le message part apres CONNECT/VCON)"
            )
        elif voice_blind or not args.wait_remote_answer:
            ring_wait = compute_ringback_wait_sec(int(args.wait_rings), float(args.ring_duration_sec))
            if ring_wait <= 0 and voice_blind:
                ring_wait = max(0.0, float(args.post_dial_wait_sec))
            ring_budget_before_serial = ring_wait

            used_audio_cue = False
            got_cue = False
            elapsed_tone = 0.0
            if args.wait_answer_tone:
                bail = float(args.answer_tone_silent_bail_sec)
                ring_cap = compute_ringback_wait_sec(int(args.wait_rings), float(args.ring_duration_sec))
                if (
                    bail > 0
                    and args.tone_fail_wait_mode == "rings"
                    and ring_cap > 0
                ):
                    capped = min(bail, ring_cap)
                    if capped < bail:
                        logger.info(
                            "answer-tone-silent-bail-sec {:.1f} s plafonne a {:.1f} s "
                            "(budget --wait-rings x --ring-duration-sec ; ligne ne sonne pas au-dela en ecoute «muette»)",
                            bail,
                            capped,
                        )
                    bail = capped
                got_cue, elapsed_tone, uart_aucun_octet = await modem.wait_voice_outbound_answer(
                    max(5.0, float(args.answer_tone_timeout_sec)),
                    silent_bail_sec=bail,
                )
                used_audio_cue = True

            if used_audio_cue:
                fail_label = "Pas d'evenement decroche sur le port (DLE+a / CONNECT / VCON / code 1)"
                if got_cue:
                    ring_wait = 0.0
                elif args.tone_fail_wait_mode == "post-dial":
                    ring_wait = max(0.0, float(args.post_dial_wait_sec))
                    logger.info(
                        "{} — repli {:.1f} s (--tone-fail-wait-mode post-dial)",
                        fail_label,
                        ring_wait,
                    )
                elif uart_aucun_octet:
                    ring_wait = 0.0
                    logger.info(
                        "{} — port serie sans aucun octet : pas de pause complementaire "
                        "(la ligne a deja sonne pendant {:.1f} s d'ecoute ; pas de delai budget-elapsed en plus)",
                        fail_label,
                        elapsed_tone,
                    )
                else:
                    ring_wait = max(0.0, ring_budget_before_serial - elapsed_tone)
                    logger.info(
                        "{} — budget avant message {:.1f} s, ecoute serie {:.1f} s → pause {:.1f} s "
                        "(--tone-fail-wait-mode rings)",
                        fail_label,
                        ring_budget_before_serial,
                        elapsed_tone,
                        ring_wait,
                    )
            if ring_wait > 0:
                if int(args.wait_rings) > 0:
                    logger.info(
                        "Pause avant message : {} sonnerie(s) estimee(s) x {:.2f} s → {:.1f} s "
                        "(--wait-rings x --ring-duration-sec){}",
                        int(args.wait_rings),
                        float(args.ring_duration_sec),
                        ring_wait,
                        " ; voice-blind" if voice_blind else "",
                    )
                elif voice_blind:
                    logger.info(
                        "Attente {:.1f} s avant le message (voice-blind / delai repli)",
                        ring_wait,
                    )
                else:
                    logger.info("Attente {:.2f} s avant le message", ring_wait)
                await asyncio.sleep(ring_wait)

        delay_pre = max(0.0, float(args.pre_play_delay_sec))
        if delay_pre:
            logger.debug("Pre-play {:.2f}s", delay_pre)
            await asyncio.sleep(delay_pre)

        logger.info("Lecture message ligne: {}", wav)
        played = await play_wav_line_fallback(
            modem,
            wav,
            prefer_already_in_voice=prefer_media,
            pcm_u8=pcm_message,
            pcm_rate=pcm_message_rate,
        )
        if not played:
            logger.warning("Lecture WAV echouee")
            exit_code = 3

        pause_post = max(0.0, float(args.post_play_pause_sec))
        if pause_post:
            await asyncio.sleep(pause_post)

        rec_sec = max(0.0, float(args.record_seconds))
        if rec_sec > 0:
            if args.beep_before_record:
                logger.info("Bip avant enregistrement ({} ms @ {} Hz)", args.beep_ms, args.beep_hz)
                with tempfile.NamedTemporaryFile(prefix="ob_beep_", suffix=".wav", delete=False) as tmp:
                    beep_path = Path(tmp.name)
                try:
                    b = _generate_beep_u8(max(60, int(args.beep_ms)), max(200, int(args.beep_hz)))
                    b += bytes([128]) * int(8000 * 0.08)
                    _write_u8_wav(beep_path, b, rate=8000)
                    await play_wav_line_fallback(modem, beep_path, prefer_already_in_voice=prefer_media)
                finally:
                    try:
                        beep_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            rec_dir = Path(args.record_dir)
            rec_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_num = args.number.replace(" ", "_").replace("/", "-")[:32]
            rec_path = rec_dir / f"outbound_{safe_num}_{stamp}.wav"
            logger.info(
                "Enregistrement ligne {} s -> {} (VRX = audio venant du correspondant sur la ligne, pas le micro PC)",
                rec_sec,
                rec_path,
            )
            timeout_rec = rec_sec + max(1.0, float(args.record_timeout_extra_sec))
            try:
                recorded = await asyncio.wait_for(
                    record_wav_line_fallback(
                        modem,
                        rec_sec,
                        rec_path,
                        prefer_already_in_voice=prefer_media,
                    ),
                    timeout=timeout_rec,
                )
            except asyncio.TimeoutError:
                logger.error("Timeout enregistrement apres {:.1f}s", timeout_rec)
                recorded = False
            if not recorded:
                logger.warning("Enregistrement echoue")
                exit_code = max(exit_code, 4)
            else:
                _enforce_wav_duration(rec_path, rec_sec)
                logger.info("Fichier enregistre: {}", rec_path)

        ok_hang, cycles = await turbo_hangup(
            modem,
            enable_console_beep=not args.quiet_hangup_tty,
            cmd_timeout=0.2,
        )
        hangup_done = True
        logger.info("Raccrochage -> ok={} cycles={}", ok_hang, cycles)
        print(f"[Hangup] cycles utilises: {cycles} | succes={ok_hang}")

        return exit_code
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
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
            except BaseException as e:
                logger.debug("Hangup final ignore ({})", type(e).__name__)
        if modem is not None:
            try:
                modem.close()
            except Exception:
                pass


if __name__ == "__main__":
    setup_logging("outbound_announce")
    raise SystemExit(asyncio.run(run()))
