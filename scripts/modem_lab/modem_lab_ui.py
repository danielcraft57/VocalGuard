#!/usr/bin/env python3
"""Interface CLI pour piloter les scenarios modem_lab."""

import json
import subprocess
import sys
from pathlib import Path

from loguru import logger
from labcore.bootstrap import setup_logging


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = PROJECT_ROOT / "scripts" / "modem_lab"
PRESETS_FILE = LAB_DIR / ".presets.json"
LAST_TTS_VOICE_FILE = LAB_DIR / ".last_tts_voice.txt"


def _run(args: list[str]) -> int:
    cmd = [sys.executable] + args
    logger.info("Execution sous-processus: {}", " ".join(cmd))
    print("\n" + "=" * 72)
    print("Execution:", " ".join(cmd))
    print("=" * 72 + "\n")
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _ask(prompt: str, default: str = "") -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw or default


def _load_presets() -> dict:
    defaults = {
        "port": "COM6",
        "default_number": "147",
        "default_voice": "fr-FR-DeniseNeural",
        "answer_delay_ms": "0",
        "last_pack_name": "default",
        "hold_seconds": "8",
        "audio_input_device": "",
        "audio_output_device": "",
        "uplink_burst_ms": "260",
        "rx_only": "y",
        "push_to_talk": "n",
        "ptt_ms": "1200",
        "voicemail_greeting_wav": str(
            LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"
        ),
        "voicemail_beep": "y",
        "voicemail_beep_pattern": "double",
        "voicemail_beep_ms": "300",
        "voicemail_beep_hz": "1000",
        "voicemail_beep2_ms": "150",
        "voicemail_beep2_hz": "780",
        "outbound_announce_wav": str(
            LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"
        ),
        "outbound_pre_play_delay_sec": "0.2",
        "outbound_post_play_pause_sec": "0.35",
        "outbound_quiet_hangup": "n",
        "outbound_wait_rings": "0",
        "outbound_ring_duration_sec": "5",
        "outbound_wait_remote_answer": "y",
        "outbound_record_seconds": "5",
        "outbound_beep_before_record": "y",
        "outbound_prepare_voice": "y",
    }
    if not PRESETS_FILE.exists():
        return defaults
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults
        defaults.update({k: str(v) for k, v in data.items()})
        return defaults
    except Exception:
        return defaults


def _save_presets(presets: dict) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.debug("Presets sauvegardes: {}", PRESETS_FILE)


def _show_header(presets: dict) -> None:
    print("\n" + "=" * 72)
    print("Modem Lab UI")
    print(f"Projet       : {PROJECT_ROOT}")
    print(f"Port         : {presets['port']}")
    print(f"Numero defaut: {presets['default_number']}")
    print(f"Voix defaut  : {presets['default_voice']}")
    print(f"Audio entrant: {'ecoute seule' if presets.get('rx_only', 'y').lower().startswith('y') else 'ecoute + micro'}")
    print("=" * 72)


def _menu_scenarios(presets: dict) -> None:
    while True:
        print("\n--- Scenarios telephonie ---")
        print("1. Smoke tests AT")
        print("2. Appel sortant simple")
        print("3. Appel sortant interactif (DTMF)")
        print("4. Attente appel entrant")
        print("5. Clavier DTMF")
        print("6. Repondeur (auto + message accueil + enregistrement)")
        print("7. Appel sortant annonce (WAV ligne puis hangup turbo)")
        print("8. Retour")
        choice = input("Choix (1-8): ").strip()

        port = presets["port"]
        number = presets["default_number"]
        delay = presets["answer_delay_ms"]
        in_dev = presets.get("audio_input_device", "")
        out_dev = presets.get("audio_output_device", "")
        burst = presets.get("uplink_burst_ms", "260")
        rx_only = presets.get("rx_only", "y")
        ptt = presets.get("push_to_talk", "n")
        ptt_ms = presets.get("ptt_ms", "1200")
        if choice == "1":
            _run([str(LAB_DIR / "labscenarios" / "smoke_tests.py"), "--port", port])
        elif choice == "2":
            number = _ask("Numero a appeler", number)
            hold = _ask("Duree avant raccroche (s)", presets.get("hold_seconds", "8"))
            presets["default_number"] = number
            presets["hold_seconds"] = hold
            _run([str(LAB_DIR / "labscenarios" / "dialer.py"), "--port", port, "--number", number, "--hold-seconds", hold])
        elif choice == "3":
            number = _ask("Numero a appeler", number)
            presets["default_number"] = number
            _run([str(LAB_DIR / "labscenarios" / "outgoing_call.py"), "--port", port, "--number", number])
        elif choice == "4":
            auto = _ask("Auto answer ? (y/n)", "y").lower().startswith("y")
            in_dev = _ask("Input device index (vide=auto)", in_dev)
            out_dev = _ask("Output device index (vide=auto)", out_dev)
            burst = _ask("Uplink burst ms", burst)
            rx_only = _ask("Rx only ? (y/n)", rx_only)
            ptt = _ask("Push-to-talk ? (y/n)", ptt)
            ptt_ms = _ask("PTT duree ms", ptt_ms)
            presets["audio_input_device"] = in_dev
            presets["audio_output_device"] = out_dev
            presets["uplink_burst_ms"] = burst
            presets["rx_only"] = rx_only
            presets["push_to_talk"] = ptt
            presets["ptt_ms"] = ptt_ms
            args = [str(LAB_DIR / "labscenarios" / "incoming_call.py"), "--port", port]
            if auto:
                delay = _ask("Delai auto answer (ms)", delay)
                presets["answer_delay_ms"] = delay
                args.extend(["--auto-answer", "--answer-delay-ms", delay])
            else:
                args.append("--manual-answer")
            args.extend(["--uplink-burst-ms", burst, "--ptt-ms", ptt_ms])
            if in_dev:
                args.extend(["--input-device", in_dev])
            if out_dev:
                args.extend(["--output-device", out_dev])
            if rx_only.lower().startswith("y"):
                args.append("--rx-only")
            if ptt.lower().startswith("y"):
                args.append("--push-to-talk")
            _run(args)
        elif choice == "5":
            number = _ask("Numero (vide si appel deja etabli)", "")
            args = [str(LAB_DIR / "labscenarios" / "dtmf_keypad.py"), "--port", port]
            if number:
                presets["default_number"] = number
                args.extend(["--number", number])
            _run(args)
        elif choice == "6":
            delay = presets.get("answer_delay_ms", "0")
            greeting = presets.get("voicemail_greeting_wav", "")
            rec_seconds = _ask(
                "Duree enregistrement message (s)",
                "5",
            )
            vm_beep = presets.get("voicemail_beep", "y")
            vm_beep_pattern = presets.get("voicemail_beep_pattern", "double").lower()
            if vm_beep_pattern not in {"single", "double"}:
                vm_beep_pattern = "double"
            vm_beep_ms = presets.get("voicemail_beep_ms", "300")
            vm_beep_hz = presets.get("voicemail_beep_hz", "1000")
            vm_beep2_ms = presets.get("voicemail_beep2_ms", "150")
            vm_beep2_hz = presets.get("voicemail_beep2_hz", "780")
            args = [
                str(LAB_DIR / "labscenarios" / "answering_machine.py"),
                "--port",
                port,
                "--answer-delay-ms",
                delay,
                "--record-seconds",
                rec_seconds,
                "--beep-pattern",
                vm_beep_pattern,
                "--beep-ms",
                vm_beep_ms,
                "--beep-hz",
                vm_beep_hz,
                "--beep2-ms",
                vm_beep2_ms,
                "--beep2-hz",
                vm_beep2_hz,
            ]
            if greeting:
                args.extend(["--greeting-wav", greeting])
            if vm_beep.lower().startswith("y"):
                args.append("--beep")
            _run(args)
        elif choice == "7":
            number = _ask("Numero a appeler", number)
            msg_wav = _ask(
                "WAV annonce ligne",
                presets.get(
                    "outbound_announce_wav",
                    str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
                ),
            )
            pre_d = _ask(
                "Pause apres compose OK avant lecture (s)",
                presets.get("outbound_pre_play_delay_sec", "0.2"),
            )
            post_p = _ask(
                "Pause apres message avant raccrochage (s)",
                presets.get("outbound_post_play_pause_sec", "0.35"),
            )
            quiet_h = presets.get("outbound_quiet_hangup", "n").lower().startswith("y")
            quiet_h = _ask("Hangup silencieux (sans bip console, y/n)", "y" if quiet_h else "n").lower().startswith(
                "y"
            )
            wait_rings = _ask(
                "Sonneries a attendre avant le WAV (0=immediat, mode aveugle seulement)",
                presets.get("outbound_wait_rings", "0"),
            )
            ring_sec = _ask(
                "Duree estimee 1 cycle sonnerie + silence (s)",
                presets.get("outbound_ring_duration_sec", "5"),
            )
            wait_ans = presets.get("outbound_wait_remote_answer", "y").lower().startswith("y")
            wait_ans = _ask("Attendre decroche distant avant message (wait-remote-answer, y/n)", "y" if wait_ans else "n").lower().startswith("y")
            rec_s = _ask(
                "Enregistrer la ligne apres le message (s, 0=non)",
                presets.get("outbound_record_seconds", "5"),
            )
            prep_v = presets.get("outbound_prepare_voice", "y").lower().startswith("y")
            prep_v = _ask("Preparation voix avant composition (+FCLASS=8 +VLS=1, y/n)", "y" if prep_v else "n").lower().startswith("y")
            beep_rec = presets.get("outbound_beep_before_record", "y").lower().startswith("y")
            beep_rec = _ask("Bip avant enregistrement si duree > 0 (y/n)", "y" if beep_rec else "n").lower().startswith("y")
            presets["default_number"] = number
            presets["outbound_announce_wav"] = msg_wav
            presets["outbound_pre_play_delay_sec"] = pre_d
            presets["outbound_post_play_pause_sec"] = post_p
            presets["outbound_quiet_hangup"] = "y" if quiet_h else "n"
            presets["outbound_wait_rings"] = wait_rings
            presets["outbound_ring_duration_sec"] = ring_sec
            presets["outbound_wait_remote_answer"] = "y" if wait_ans else "n"
            presets["outbound_record_seconds"] = rec_s
            presets["outbound_prepare_voice"] = "y" if prep_v else "n"
            presets["outbound_beep_before_record"] = "y" if beep_rec else "n"
            args = [
                str(LAB_DIR / "labscenarios" / "outbound_announce.py"),
                "--port",
                port,
                "--number",
                number,
                "--message-wav",
                msg_wav,
                "--pre-play-delay-sec",
                pre_d,
                "--post-play-pause-sec",
                post_p,
                "--wait-rings",
                wait_rings,
                "--ring-duration-sec",
                ring_sec,
            ]
            if wait_ans:
                args.append("--wait-remote-answer")
            if not prep_v:
                args.append("--no-prepare-voice-line")
            try:
                rs = float(rec_s.replace(",", "."))
            except ValueError:
                rs = 0.0
            if rs > 0:
                args.extend(["--record-seconds", str(rs)])
                if beep_rec:
                    args.append("--beep-before-record")
            if quiet_h:
                args.append("--quiet-hangup-tty")
            _run(args)
        elif choice == "8":
            return
        else:
            print("Choix invalide.")


def _menu_audio(presets: dict) -> None:
    while True:
        print("\n--- Audio / TTS ---")
        print("1. Lister/choisir une voix (menu TTS)")
        print("2. Generer un pack audio modem")
        print("3. Retour")
        choice = input("Choix (1-3): ").strip()

        if choice == "1":
            _run(
                [
                    str(LAB_DIR / "tts_engine_copy.py"),
                    "--selection-file",
                    str(LAST_TTS_VOICE_FILE),
                    "--initial-voice",
                    presets["default_voice"],
                ]
            )
            if LAST_TTS_VOICE_FILE.exists():
                selected_voice = LAST_TTS_VOICE_FILE.read_text(encoding="utf-8").strip()
                if selected_voice:
                    presets["default_voice"] = selected_voice
                    logger.info("Voix par defaut mise a jour depuis menu TTS: {}", selected_voice)
                    _save_presets(presets)
        elif choice == "2":
            voice = _ask("Voix edge-tts", presets["default_voice"])
            pack_name = _ask("Nom du pack", presets["last_pack_name"])
            presets["default_voice"] = voice
            presets["last_pack_name"] = pack_name
            _run(
                [
                    str(LAB_DIR / "generate_modem_sounds.py"),
                    "--voice",
                    voice,
                    "--pack-name",
                    pack_name,
                ]
            )
        elif choice == "3":
            return
        else:
            print("Choix invalide.")


def _menu_config(presets: dict) -> None:
    print("\n--- Configuration ---")
    presets["port"] = _ask("Port modem", presets["port"])
    presets["default_number"] = _ask("Numero par defaut", presets["default_number"])
    presets["default_voice"] = _ask("Voix par defaut", presets["default_voice"])
    presets["answer_delay_ms"] = _ask("Delai auto-answer (ms)", presets["answer_delay_ms"])
    presets["hold_seconds"] = _ask("Duree dialer hold (s)", presets.get("hold_seconds", "8"))
    presets["audio_input_device"] = _ask("Input device index", presets.get("audio_input_device", ""))
    presets["audio_output_device"] = _ask("Output device index", presets.get("audio_output_device", ""))
    presets["uplink_burst_ms"] = _ask("Uplink burst ms", presets.get("uplink_burst_ms", "260"))
    presets["rx_only"] = _ask("Rx only (y/n)", presets.get("rx_only", "y"))
    presets["push_to_talk"] = _ask("Push-to-talk (y/n)", presets.get("push_to_talk", "n"))
    presets["ptt_ms"] = _ask("PTT duree ms", presets.get("ptt_ms", "1200"))
    presets["voicemail_greeting_wav"] = _ask(
        "WAV message accueil repondeur",
        presets.get("voicemail_greeting_wav", ""),
    )
    presets["voicemail_beep"] = _ask("Bip repondeur (y/n)", presets.get("voicemail_beep", "y"))
    presets["voicemail_beep_pattern"] = _ask(
        "Pattern bip (single/double)",
        presets.get("voicemail_beep_pattern", "double"),
    )
    presets["voicemail_beep_ms"] = _ask("Duree bip (ms)", presets.get("voicemail_beep_ms", "300"))
    presets["voicemail_beep_hz"] = _ask("Frequence bip (Hz)", presets.get("voicemail_beep_hz", "1000"))
    presets["voicemail_beep2_ms"] = _ask("Duree bip 2 (ms)", presets.get("voicemail_beep2_ms", "150"))
    presets["voicemail_beep2_hz"] = _ask("Frequence bip 2 (Hz)", presets.get("voicemail_beep2_hz", "780"))
    presets["outbound_announce_wav"] = _ask(
        "WAV appel sortant annonce (defaut menu 7)",
        presets.get(
            "outbound_announce_wav",
            str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
        ),
    )
    presets["outbound_pre_play_delay_sec"] = _ask(
        "Pause pre-lecture outbound (s)",
        presets.get("outbound_pre_play_delay_sec", "0.2"),
    )
    presets["outbound_post_play_pause_sec"] = _ask(
        "Pause post-lecture outbound (s)",
        presets.get("outbound_post_play_pause_sec", "0.35"),
    )
    presets["outbound_quiet_hangup"] = _ask(
        "Hangup outbound sans bip console (y/n)",
        presets.get("outbound_quiet_hangup", "n"),
    )
    presets["outbound_wait_rings"] = _ask(
        "Outbound: sonneries avant WAV (0=immediat)",
        presets.get("outbound_wait_rings", "0"),
    )
    presets["outbound_ring_duration_sec"] = _ask(
        "Outbound: duree 1 cycle sonnerie (s)",
        presets.get("outbound_ring_duration_sec", "5"),
    )
    presets["outbound_wait_remote_answer"] = _ask(
        "Outbound: attendre decroche (y/n)",
        presets.get("outbound_wait_remote_answer", "y"),
    )
    presets["outbound_record_seconds"] = _ask(
        "Outbound: enregistrement apres message (s, 0=non)",
        presets.get("outbound_record_seconds", "5"),
    )
    presets["outbound_prepare_voice"] = _ask(
        "Outbound: prep voix +VLS=1 avant compo (y/n)",
        presets.get("outbound_prepare_voice", "y"),
    )
    presets["outbound_beep_before_record"] = _ask(
        "Outbound: bip avant enregistrement (y/n)",
        presets.get("outbound_beep_before_record", "y"),
    )
    _save_presets(presets)
    print("Configuration sauvegardee.")


def main() -> int:
    setup_logging("modem_lab_ui")
    logger.info("Demarrage interface modem_lab_ui")
    presets = _load_presets()
    _save_presets(presets)

    while True:
        _show_header(presets)
        print("\n--- Menu principal ---")
        print("1. Scenarios telephonie")
        print("2. Audio / TTS")
        print("3. Configuration")
        print("4. Ouvrir README modem_lab")
        print("5. Quitter")
        choice = input("Choix (1-5): ").strip()

        if choice == "1":
            logger.debug("Menu principal -> Scenarios telephonie")
            _menu_scenarios(presets)
            _save_presets(presets)
        elif choice == "2":
            logger.debug("Menu principal -> Audio/TTS")
            _menu_audio(presets)
            _save_presets(presets)
        elif choice == "3":
            logger.debug("Menu principal -> Configuration")
            _menu_config(presets)
        elif choice == "4":
            logger.debug("Menu principal -> Ouvrir README")
            readme = LAB_DIR / "README.md"
            print("\nREADME:", readme, "\n")
            if readme.exists():
                print(readme.read_text(encoding="utf-8"))
            else:
                print("README introuvable.")
        elif choice == "5":
            logger.info("Fermeture modem_lab_ui")
            return 0
        else:
            print("Choix invalide.")


if __name__ == "__main__":
    raise SystemExit(main())
