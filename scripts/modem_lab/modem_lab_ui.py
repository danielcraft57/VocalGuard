#!/usr/bin/env python3
"""
Modem Lab — interface terminal (Rich + Questionary).

Point d’entrée conseillé ::
    python scripts/modem_lab/modem_lab_ui.py

Pour générer les WAV d’intents **sans** cette UI (équivalent menu « Pack intents ») ::
    python scripts/modem_lab/labaudio/generate_intent_pack.py ^
      --intents data/intents_prospection_flow.json ^
      --out scripts/modem_lab/generated/prospection_pack/demo ^
      --voice fr-FR-DeniseNeural ^
      --var agent_name=Alex --var company_name=MaBoite

Les arguments ``--out`` / ``--var`` sont pour **generate_intent_pack**, pas pour ``prospection_outbound``.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = PROJECT_ROOT / "scripts" / "modem_lab"
PRESETS_FILE = LAB_DIR / ".presets.json"
LAST_TTS_VOICE_FILE = LAB_DIR / ".last_tts_voice.txt"

sys.path.insert(0, str(LAB_DIR))

from labcore.bootstrap import setup_logging

# Style Questionary partagé (rempli au démarrage de ``main``).
_UI: dict[str, Any] = {"q_style": None}


def _register_questionary_style(style: object) -> None:
    _UI["q_style"] = style


def _build_questionary_style(questionary: Any) -> Any:
    """Palette type « One Dark » lisible sur fond sombre (Cursor / Windows Terminal)."""
    return questionary.Style(
        [
            ("qmark", "fg:#61afef bold"),
            ("question", "bold fg:#e5c07b"),
            ("answer", "fg:#98c379"),
            ("pointer", "fg:#61afef bold"),
            ("highlighted", "fg:#c678dd bold"),
            ("selected", "fg:#98c379 bold"),
            ("instruction", "fg:#abb2bf"),
        ]
    )


def _q_kwargs() -> dict[str, Any]:
    st = _UI.get("q_style")
    return {"style": st} if st is not None else {}


def _require_tui_deps() -> tuple["Console", "Theme", type]:
    """Charge Rich + Questionary ou quitte avec message clair."""
    try:
        from rich.console import Console
        from rich.theme import Theme
        import questionary
    except ImportError as e:
        print(
            "Dépendances TUI manquantes. Installez :\n"
            "  pip install rich questionary\n"
            f"Détail : {e}",
            file=sys.stderr,
        )
        raise SystemExit(2) from e
    theme = Theme(
        {
            "info": "cyan",
            "warn": "yellow",
            "err": "bold red",
            "ok": "bold green",
            "title": "bold magenta",
            "muted": "dim",
        }
    )
    console = Console(theme=theme, highlight=True)
    return console, theme, questionary


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
        "intent_pack_last_rel": "data/intents_prospection_flow.json",
        "intent_pack_out_rel": str(LAB_DIR / "generated" / "prospection_pack" / "ui_pack"),
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
    logger.debug("Presets sauvegardés: {}", PRESETS_FILE)


def _run_sub(console, args: list[str]) -> int:
    cmd = [sys.executable] + args
    line = " ".join(shlex.quote(str(a)) for a in cmd)
    logger.info("Sous-processus: {}", line)
    from rich.panel import Panel

    console.print()
    console.print(Panel(line, title="[bold cyan]Commande[/]", border_style="cyan"))
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def _ask_text(
    questionary,
    presets: dict,
    prompt: str,
    key: str,
    override: str | None = None,
) -> str:
    """Prompt avec défaut = preset[key] ou ``override`` pour ce tour."""
    d = str(override if override is not None else presets.get(key, ""))
    r = questionary.text(prompt, default=d, **_q_kwargs()).ask()
    if r is None:
        return d
    return r


def _pause(console) -> None:
    console.print("[dim]↵ Entrée pour continuer…[/]")
    try:
        input()
    except EOFError:
        pass


def _pad_vertical_lines(
    console,
    *,
    fraction: float = 0.35,
    cap: int = 42,
    floor_n: int = 0,
) -> None:
    """
    Imprime des lignes vides pour occuper une fraction de la hauteur du terminal
    (effet « plein écran » dans les consoles intégrées type Cursor / VS Code).
    """
    try:
        h = int(console.size.height)
    except Exception:
        h = 24
    h = max(12, h)
    n = int(h * max(0.0, min(0.85, fraction)))
    n = max(floor_n, min(cap, n))
    if n > 0:
        console.print("\n" * n, end="")


def _section_header(console, title: str, subtitle: str = "") -> None:
    """Séparateur visuel avant un bloc Questionary."""
    from rich.rule import Rule
    from rich.text import Text

    console.print()
    console.print(Rule(f"[bold bright_cyan]{title}[/]", style="cyan"))
    if subtitle:
        console.print(Text(subtitle, style="dim italic"))
    console.print()


def _draw_home_banner(console, presets: dict) -> None:
    """Bannière d’accueil : synthèse des presets dans un tableau."""
    from rich import box
    from rich.align import Align
    from rich.panel import Panel
    from rich.table import Table

    tbl = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", expand=False)
    tbl.add_column("Réglage", style="dim", min_width=14, no_wrap=True)
    tbl.add_column("Valeur", style="white")
    tbl.add_row("Port modem", str(presets.get("port", "")))
    tbl.add_row("Numéro par défaut", str(presets.get("default_number", "")))
    tbl.add_row("Voix edge-tts", str(presets.get("default_voice", "")))
    tbl.add_row("Dossier projet", str(PROJECT_ROOT))
    inner = Panel(
        tbl,
        title="[bold magenta]VocalGuard[/]  [white]Modem Lab[/]",
        subtitle="[dim]Presets : scripts/modem_lab/.presets.json  ·  logs : scripts/modem_lab/logs[/]",
        border_style="bright_magenta",
        box=box.DOUBLE,
    )
    console.print(Align.center(inner))


def _select(console, questionary, message: str, choices: list, *, instruction: str | None = None, **extra):
    """``select`` Questionary isolé du rendu Rich (évite titres collés / artefacts terminal)."""
    console.print()
    kw: dict[str, Any] = dict(_q_kwargs())
    kw["instruction"] = instruction or "(↑↓ puis Entrée · Échap annule)"
    kw.update(extra)
    return questionary.select(message, choices=choices, **kw).ask()


def _confirm(questionary, message: str, *, default: bool = True) -> bool:
    r = questionary.confirm(message, default=default, **_q_kwargs()).ask()
    return bool(r) if r is not None else default


def _text_raw(questionary, message: str, *, default: str = "") -> str:
    r = questionary.text(message, default=default, **_q_kwargs()).ask()
    return (r if r is not None else default) or ""


def _panel_cli_intents(console) -> None:
    """Rappel CLI pour éviter la confusion avec prospection_outbound."""
    from rich.markdown import Markdown
    from rich.panel import Panel

    md = Markdown(
        "### Générer les WAV (pack intents)\n\n"
        "**Script :** `scripts/modem_lab/labaudio/generate_intent_pack.py`\n\n"
        "```text\n"
        "python scripts/modem_lab/labaudio/generate_intent_pack.py \\\n"
        "  --intents data/intents_prospection_flow.json \\\n"
        "  --out scripts/modem_lab/generated/prospection_pack/demo \\\n"
        "  --voice fr-FR-DeniseNeural \\\n"
        "  --var agent_name=Alex --var company_name=MaBoite\n"
        "```\n\n"
        "**Appel prospection** (modem + STT) : `cli.py prospection-outbound` — "
        "**sans** `--out` ni `--var`."
    )
    console.print(Panel(md, title="[bold]Aide CLI intents[/]", border_style="blue"))


def menu_intent_pack_wizard(console, questionary, presets: dict) -> None:
    """Assistant : JSON dans data/, voix edge-tts, placeholders {{…}}."""
    from labaudio.intent_wav_pack import (
        build_pack_from_json,
        collect_placeholder_keys_from_intent_json,
        load_placeholders_json,
    )
    from rich.panel import Panel

    data_dir = PROJECT_ROOT / "data"
    if not data_dir.is_dir():
        console.print("[err]Dossier data/ introuvable.[/]")
        _pause(console)
        return

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        console.print("[warn]Aucun fichier *.json dans data/.[/]")
        _pause(console)
        return

    _section_header(console, "Assistant pack intents", "Un WAV par réponse dans le JSON · 8 kHz mono")
    json_choices = [
        questionary.Choice(
            title=f"{p.name}  ({max(1, p.stat().st_size // 1024)} Ko)",
            value=str(p.resolve()),
        )
        for p in json_files
    ]
    default_sel = (presets.get("intent_pack_last_rel") or "").replace("\\", "/")
    default_path = next(
        (str(p.resolve()) for p in json_files if default_sel.endswith(p.name)),
        str(json_files[0].resolve()),
    )

    _pad_vertical_lines(console, fraction=0.06, cap=6)
    sel = _select(
        console,
        questionary,
        "Fichier d’intents (dossier data/)",
        json_choices,
        default=default_path,
    )
    if not sel:
        return

    intent_path = Path(sel)
    try:
        presets["intent_pack_last_rel"] = str(intent_path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        presets["intent_pack_last_rel"] = str(intent_path)

    voice = _ask_text(questionary, presets, "Voix edge-tts", "default_voice")
    presets["default_voice"] = voice

    out_preset = (presets.get("intent_pack_out_rel") or "").strip()
    if out_preset:
        out_default = Path(out_preset)
    else:
        out_default = LAB_DIR / "generated" / "prospection_pack" / intent_path.stem
    out_s = _text_raw(
        questionary,
        "Dossier de sortie des WAV (8 kHz)",
        default=str(out_default.resolve()),
    )
    out_path = Path(out_s.strip() if out_s else str(out_default.resolve()))
    presets["intent_pack_out_rel"] = str(out_path.resolve())

    vars_json_s = (
        _text_raw(
            questionary,
            "JSON placeholders optionnel (chemin relatif au dépôt ou absolu, vide = aucun)",
            default="",
        ).strip()
    )
    if vars_json_s:
        _vp = Path(vars_json_s)
        vars_json = _vp.resolve() if _vp.is_absolute() else (PROJECT_ROOT / _vp).resolve()
    else:
        vars_json = None

    keys = collect_placeholder_keys_from_intent_json(intent_path)
    placeholders = load_placeholders_json(vars_json if vars_json and vars_json.is_file() else None)

    if keys:
        console.print(Panel(", ".join(f"{{{{{k}}}}}" for k in keys), title="Placeholders détectés"))
        mode = _select(
            console,
            questionary,
            "Placeholders {{…}} détectés — comment les remplir ?",
            [
                questionary.Choice("Saisie guidée (recommandé)", value="guided"),
                questionary.Choice("Ignorer (laisser les {{…}} tels quels)", value="skip"),
            ],
            default="guided",
        )
        if mode == "guided":
            for k in keys:
                cur = placeholders.get(k, "")
                v = _text_raw(questionary, f"Valeur pour « {k} »", default=cur)
                placeholders[k] = v or ""

    force = _confirm(questionary, "Régénérer tous les WAV même s’ils existent déjà ?", default=False)
    force_b = bool(force)

    console.print("[info]Génération en cours (edge-tts + pydub)…[/]")
    try:

        async def _go() -> None:
            await build_pack_from_json(
                intent_path,
                out_path,
                placeholders,
                voice=voice,
                force=force_b,
            )

        asyncio.run(_go())
    except Exception as e:
        console.print(f"[err]Échec : {e}[/]")
        logger.exception("intent pack")
        _pause(console)
        return

    def _rel_to_repo(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError:
            return str(p.resolve())

    rel_cmd = (
        "python scripts/modem_lab/labaudio/generate_intent_pack.py "
        f'--intents "{_rel_to_repo(intent_path)}" '
        f'--out "{_rel_to_repo(out_path)}" '
        f"--voice {shlex.quote(voice)}"
    )
    if vars_json and vars_json.is_file():
        rel_cmd += f' --vars-json "{_rel_to_repo(vars_json)}"'
    console.print("[ok]Pack généré.[/]")
    console.print(Panel(rel_cmd, title="Équivalent ligne de commande", border_style="green"))
    _save_presets(presets)
    _pause(console)


def menu_audio(console, questionary, presets: dict) -> None:
    while True:
        _section_header(console, "Audio & TTS", "Voix Microsoft edge-tts · packs modem · intents → WAV 8 kHz")
        ch = _select(
            console,
            questionary,
            "Action",
            [
                questionary.Choice("Choisir / tester une voix (menu edge-tts)", value="voice"),
                questionary.Choice("Générer pack audio modem (sound_pack)", value="modem"),
                questionary.Choice("Pack WAV depuis intents (fichiers data/*.json)", value="intents"),
                questionary.Choice("Aide : CLI intents vs prospection-outbound", value="help_cli"),
                questionary.Choice("Retour au menu principal", value="back"),
            ],
        )
        if ch is None or ch == "back":
            return

        if ch == "voice":
            _run_sub(
                console,
                [
                    str(LAB_DIR / "tts_engine_copy.py"),
                    "--selection-file",
                    str(LAST_TTS_VOICE_FILE),
                    "--initial-voice",
                    presets["default_voice"],
                ],
            )
            if LAST_TTS_VOICE_FILE.exists():
                selected = LAST_TTS_VOICE_FILE.read_text(encoding="utf-8").strip()
                if selected:
                    presets["default_voice"] = selected
                    _save_presets(presets)

        elif ch == "modem":
            voice = _ask_text(questionary, presets, "Voix edge-tts", "default_voice")
            pack_name = _ask_text(questionary, presets, "Nom du sous-dossier pack", "last_pack_name")
            presets["default_voice"] = voice
            presets["last_pack_name"] = pack_name
            _save_presets(presets)
            _run_sub(
                console,
                [
                    str(LAB_DIR / "generate_modem_sounds.py"),
                    "--voice",
                    voice,
                    "--pack-name",
                    pack_name,
                ],
            )

        elif ch == "intents":
            menu_intent_pack_wizard(console, questionary, presets)

        elif ch == "help_cli":
            _panel_cli_intents(console)
            _pause(console)


def menu_scenarios(console, questionary, presets: dict) -> None:
    """Menus scénarios (logique inchangée, prompts Questionary)."""
    port = presets["port"]
    number = presets["default_number"]
    delay = presets["answer_delay_ms"]

    while True:
        _section_header(console, "Scénarios modem", "USB / AT+VRX / scripts labscenarios")
        ch = _select(
            console,
            questionary,
            "Scénario à lancer",
            [
                questionary.Choice("Smoke tests AT", value="1"),
                questionary.Choice("Dialer — appel sortant simple", value="2"),
                questionary.Choice("Outgoing + clavier DTMF", value="3"),
                questionary.Choice("Appel entrant (pont audio)", value="4"),
                questionary.Choice("DTMF keypad (ligne établie)", value="5"),
                questionary.Choice("Répondeur entrant", value="6"),
                questionary.Choice("Outbound announce (WAV sur la ligne)", value="7"),
                questionary.Choice("Retour au menu principal", value="back"),
            ],
        )
        if ch is None or ch == "back":
            return

        if ch == "1":
            _run_sub(console, [str(LAB_DIR / "labscenarios" / "smoke_tests.py"), "--port", port])

        elif ch == "2":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            hold = _ask_text(questionary, presets, "Durée avant raccrochage (s)", "hold_seconds")
            presets["default_number"] = number
            presets["hold_seconds"] = hold
            _save_presets(presets)
            _run_sub(
                console,
                [
                    str(LAB_DIR / "labscenarios" / "dialer.py"),
                    "--port",
                    port,
                    "--number",
                    number,
                    "--hold-seconds",
                    hold,
                ],
            )

        elif ch == "3":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            presets["default_number"] = number
            _save_presets(presets)
            _run_sub(
                console,
                [str(LAB_DIR / "labscenarios" / "outgoing_call.py"), "--port", port, "--number", number],
            )

        elif ch == "4":
            in_dev = presets.get("audio_input_device", "")
            out_dev = presets.get("audio_output_device", "")
            burst = presets.get("uplink_burst_ms", "260")
            rx_only = presets.get("rx_only", "y")
            ptt = presets.get("push_to_talk", "n")
            ptt_ms = presets.get("ptt_ms", "1200")
            auto = _confirm(questionary, "Réponse automatique à la sonnerie ?", default=True)
            in_dev = _ask_text(
                questionary,
                presets,
                "Index entrée audio (vide=auto)",
                "audio_input_device",
                override=in_dev,
            )
            out_dev = _ask_text(
                questionary,
                presets,
                "Index sortie audio (vide=auto)",
                "audio_output_device",
                override=out_dev,
            )
            burst = _ask_text(questionary, presets, "Uplink burst (ms)", "uplink_burst_ms", override=burst)
            rx_only = _ask_text(questionary, presets, "Rx only (y/n)", "rx_only", override=rx_only)
            ptt = _ask_text(questionary, presets, "Push-to-talk (y/n)", "push_to_talk", override=ptt)
            ptt_ms = _ask_text(questionary, presets, "Durée PTT (ms)", "ptt_ms", override=ptt_ms)
            presets.update(
                {
                    "audio_input_device": in_dev,
                    "audio_output_device": out_dev,
                    "uplink_burst_ms": burst,
                    "rx_only": rx_only,
                    "push_to_talk": ptt,
                    "ptt_ms": ptt_ms,
                }
            )
            args = [str(LAB_DIR / "labscenarios" / "incoming_call.py"), "--port", port]
            if auto:
                delay = _ask_text(questionary, presets, "Délai auto answer (ms)", "answer_delay_ms", override=delay)
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
            _save_presets(presets)
            _run_sub(console, args)

        elif ch == "5":
            num_in = _text_raw(questionary, "Numéro (vide si ligne déjà établie)", default="")
            args = [str(LAB_DIR / "labscenarios" / "dtmf_keypad.py"), "--port", port]
            if num_in.strip():
                presets["default_number"] = num_in.strip()
                args.extend(["--number", num_in.strip()])
            _save_presets(presets)
            _run_sub(console, args)

        elif ch == "6":
            delay = presets.get("answer_delay_ms", "0")
            greeting = presets.get("voicemail_greeting_wav", "")
            rec_seconds = _text_raw(questionary, "Durée enregistrement message (s)", default="5") or "5"
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
            _run_sub(console, args)

        elif ch == "7":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            msg_wav = _ask_text(
                questionary,
                presets,
                "Fichier WAV annonce",
                "outbound_announce_wav",
                override=presets.get(
                    "outbound_announce_wav",
                    str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
                ),
            )
            pre_d = _ask_text(questionary, presets, "Pause après compose OK (s)", "outbound_pre_play_delay_sec")
            post_p = _ask_text(questionary, presets, "Pause après message (s)", "outbound_post_play_pause_sec")
            quiet_h = _confirm(questionary, "Hangup console silencieux ?", default=False)
            wait_rings = _ask_text(questionary, presets, "Sonneries avant WAV", "outbound_wait_rings")
            ring_sec = _ask_text(questionary, presets, "Durée cycle sonnerie (s)", "outbound_ring_duration_sec")
            wait_ans = _confirm(questionary, "Attendre décroché distant (wait-remote-answer) ?", default=True)
            rec_s = _ask_text(questionary, presets, "Enregistrement après message (s, 0=non)", "outbound_record_seconds")
            prep_v = _confirm(questionary, "Préparation voix +VLS=1 ?", default=True)
            beep_rec = _confirm(questionary, "Bip avant enregistrement si durée > 0 ?", default=True)
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
            _save_presets(presets)
            _run_sub(console, args)


def menu_config(console, questionary, presets: dict) -> None:
    _section_header(console, "Configuration des presets", "Écrit dans scripts/modem_lab/.presets.json")
    presets["port"] = _ask_text(questionary, presets, "Port modem", "port")
    presets["default_number"] = _ask_text(questionary, presets, "Numéro par défaut", "default_number")
    presets["default_voice"] = _ask_text(questionary, presets, "Voix edge-tts par défaut", "default_voice")
    presets["answer_delay_ms"] = _ask_text(questionary, presets, "Délai auto-answer (ms)", "answer_delay_ms")
    presets["hold_seconds"] = _ask_text(questionary, presets, "Dialer hold (s)", "hold_seconds")
    presets["audio_input_device"] = _ask_text(questionary, presets, "Input device index", "audio_input_device")
    presets["audio_output_device"] = _ask_text(questionary, presets, "Output device index", "audio_output_device")
    presets["uplink_burst_ms"] = _ask_text(questionary, presets, "Uplink burst ms", "uplink_burst_ms")
    presets["rx_only"] = _ask_text(questionary, presets, "Rx only (y/n)", "rx_only")
    presets["push_to_talk"] = _ask_text(questionary, presets, "Push-to-talk (y/n)", "push_to_talk")
    presets["ptt_ms"] = _ask_text(questionary, presets, "PTT ms", "ptt_ms")
    presets["voicemail_greeting_wav"] = _ask_text(questionary, presets, "WAV répondeur", "voicemail_greeting_wav")
    presets["voicemail_beep"] = _ask_text(questionary, presets, "Bip répondeur (y/n)", "voicemail_beep")
    presets["voicemail_beep_pattern"] = _ask_text(questionary, presets, "Pattern bip", "voicemail_beep_pattern")
    presets["voicemail_beep_ms"] = _ask_text(questionary, presets, "Bip ms", "voicemail_beep_ms")
    presets["voicemail_beep_hz"] = _ask_text(questionary, presets, "Bip Hz", "voicemail_beep_hz")
    presets["voicemail_beep2_ms"] = _ask_text(questionary, presets, "Bip2 ms", "voicemail_beep2_ms")
    presets["voicemail_beep2_hz"] = _ask_text(questionary, presets, "Bip2 Hz", "voicemail_beep2_hz")
    presets["outbound_announce_wav"] = _ask_text(questionary, presets, "WAV outbound", "outbound_announce_wav")
    presets["outbound_pre_play_delay_sec"] = _ask_text(questionary, presets, "Outbound pré-lecture", "outbound_pre_play_delay_sec")
    presets["outbound_post_play_pause_sec"] = _ask_text(questionary, presets, "Outbound post-lecture", "outbound_post_play_pause_sec")
    presets["outbound_quiet_hangup"] = _ask_text(questionary, presets, "Outbound hangup silencieux", "outbound_quiet_hangup")
    presets["outbound_wait_rings"] = _ask_text(questionary, presets, "Outbound sonneries", "outbound_wait_rings")
    presets["outbound_ring_duration_sec"] = _ask_text(questionary, presets, "Outbound cycle sonnerie", "outbound_ring_duration_sec")
    presets["outbound_wait_remote_answer"] = _ask_text(questionary, presets, "Outbound wait remote", "outbound_wait_remote_answer")
    presets["outbound_record_seconds"] = _ask_text(questionary, presets, "Outbound record s", "outbound_record_seconds")
    presets["outbound_prepare_voice"] = _ask_text(questionary, presets, "Outbound prep voix", "outbound_prepare_voice")
    presets["outbound_beep_before_record"] = _ask_text(questionary, presets, "Outbound bip record", "outbound_beep_before_record")
    _save_presets(presets)
    console.print("[ok]Configuration enregistrée.[/]")


def main() -> int:
    console, _theme, questionary = _require_tui_deps()

    setup_logging("modem_lab_ui")
    logger.info("Démarrage Modem Lab UI (Rich)")

    _register_questionary_style(_build_questionary_style(questionary))

    presets = _load_presets()
    _save_presets(presets)

    _pad_vertical_lines(console, fraction=0.10, cap=12, floor_n=1)
    _draw_home_banner(console, presets)
    _pad_vertical_lines(console, fraction=0.05, cap=6, floor_n=1)

    while True:
        _section_header(console, "Menu principal", "Laboratoire modem USB — VocalGuard")
        ch = _select(
            console,
            questionary,
            "Que veux-tu faire ?",
            [
                questionary.Choice("Scénarios modem (smoke, dialer, entrant, DTMF…)", value="scen"),
                questionary.Choice("Audio, TTS & packs WAV (intents data/)", value="audio"),
                questionary.Choice("Réglages port / numéro / voix / WAV", value="cfg"),
                questionary.Choice("Lire un extrait du README modem_lab", value="readme"),
                questionary.Choice("Quitter", value="quit"),
            ],
        )

        if ch is None or ch == "quit":
            console.print("[muted]À bientôt.[/]")
            return 0

        if ch == "scen":
            menu_scenarios(console, questionary, presets)
            _save_presets(presets)
        elif ch == "audio":
            menu_audio(console, questionary, presets)
            _save_presets(presets)
        elif ch == "cfg":
            menu_config(console, questionary, presets)
        elif ch == "readme":
            from rich.panel import Panel

            readme = LAB_DIR / "README.md"
            if readme.exists():
                text = readme.read_text(encoding="utf-8")
                excerpt = "\n".join(text.splitlines()[:48])
                console.print(Panel(excerpt, title=str(readme), border_style="blue", expand=False))
            else:
                console.print("[warn]README introuvable.[/]")
            _pause(console)


if __name__ == "__main__":
    raise SystemExit(main())
