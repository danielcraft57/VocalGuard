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
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = PROJECT_ROOT / "scripts" / "modem_lab"
PRESETS_FILE = LAB_DIR / ".presets.json"
LAST_TTS_VOICE_FILE = LAB_DIR / ".last_tts_voice.txt"

sys.path.insert(0, str(LAB_DIR))

from labcore.bootstrap import setup_logging
from labcore.scenario_bookmarks import (
    bookmarks_file,
    load_bookmarks,
    save_bookmarks,
    validate_bookmark_id,
)

import cli as modem_lab_cli

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
        "intent_pack_meta_subtitle": "",
        "intent_pack_meta_year": "",
        "intent_pack_meta_track_number": "",
        "intent_pack_meta_genre": "",
        "intent_pack_meta_media_origin": "VocalGuard modem_lab",
        "intent_pack_meta_copyright": "",
        "intent_pack_meta_parental_control": "",
        "intent_pack_meta_parental_reason": "",
        "vosk_model_slug": "small-fr",
        "answer_vosk_listen_sec": "40",
        "subtitle_timeline_offset_sec": "0",
        "answer_vosk_srt_origin_first_ring": "y",
        "outbound_vad_listen_sec": "90",
        "prompt_play_sequence": "welcome",
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


def _run_cli_target(console, target: str, tail: list[str]) -> int:
    """Lance un scénario intégré ou un **signet** via ``cli.py``."""
    args: list[str] = [str(LAB_DIR / "cli.py"), target]
    if tail:
        args.append("--")
        args.extend(str(x) for x in tail)
    return _run_sub(console, args)


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

    _section_header(console, "Métadonnées WAV (UI pack)", "Champs RIFF additionnels")
    meta_subtitle = _ask_text(questionary, presets, "Sous-titre (ISBJ)", "intent_pack_meta_subtitle")
    current_year = str(datetime.now().year)
    year_default = str(presets.get("intent_pack_meta_year", "")).strip() or current_year
    meta_year = _ask_text(
        questionary,
        presets,
        "Année (ICRD)",
        "intent_pack_meta_year",
        override=year_default,
    )
    meta_track = _ask_text(questionary, presets, "N° (ITRK)", "intent_pack_meta_track_number")
    meta_genre = _ask_text(questionary, presets, "Genre (IGNR)", "intent_pack_meta_genre")
    meta_origin = _ask_text(questionary, presets, "Origine média (ISRC)", "intent_pack_meta_media_origin")
    meta_copyright = _ask_text(questionary, presets, "Copyright (ICOP)", "intent_pack_meta_copyright")
    meta_parental = _ask_text(
        questionary,
        presets,
        "Contenu contrôle parental (ex: yes/no/all_ages)",
        "intent_pack_meta_parental_control",
    )
    meta_parental_reason = _ask_text(
        questionary,
        presets,
        "Motif du contrôle parental",
        "intent_pack_meta_parental_reason",
    )
    presets["intent_pack_meta_subtitle"] = meta_subtitle
    presets["intent_pack_meta_year"] = meta_year
    presets["intent_pack_meta_track_number"] = meta_track
    presets["intent_pack_meta_genre"] = meta_genre
    presets["intent_pack_meta_media_origin"] = meta_origin
    presets["intent_pack_meta_copyright"] = meta_copyright
    presets["intent_pack_meta_parental_control"] = meta_parental
    presets["intent_pack_meta_parental_reason"] = meta_parental_reason

    console.print("[info]Génération en cours (edge-tts + pydub)…[/]")
    try:

        async def _go() -> None:
            await build_pack_from_json(
                intent_path,
                out_path,
                placeholders,
                voice=voice,
                force=force_b,
                metadata={
                    "subtitle": meta_subtitle,
                    "year": meta_year,
                    "track_number": meta_track,
                    "genre": meta_genre,
                    "media_origin": meta_origin,
                    "copyright_text": meta_copyright,
                    "parental_control": meta_parental,
                    "parental_control_reason": meta_parental_reason,
                },
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
    if meta_subtitle.strip():
        rel_cmd += f" --subtitle {shlex.quote(meta_subtitle.strip())}"
    if meta_year.strip():
        rel_cmd += f" --year {shlex.quote(meta_year.strip())}"
    if meta_track.strip():
        rel_cmd += f" --track-number {shlex.quote(meta_track.strip())}"
    if meta_genre.strip():
        rel_cmd += f" --genre {shlex.quote(meta_genre.strip())}"
    if meta_origin.strip():
        rel_cmd += f" --media-origin {shlex.quote(meta_origin.strip())}"
    if meta_copyright.strip():
        rel_cmd += f" --copyright-text {shlex.quote(meta_copyright.strip())}"
    if meta_parental.strip():
        rel_cmd += f" --parental-control {shlex.quote(meta_parental.strip())}"
    if meta_parental_reason.strip():
        rel_cmd += f" --parental-control-reason {shlex.quote(meta_parental_reason.strip())}"
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


def menu_scenario_bookmarks(console, questionary, presets: dict) -> None:
    """Lister / ajouter / modifier / supprimer / lancer des signets ``cli.py``."""
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    builtins = set(modem_lab_cli.SCENARIO_MAP.keys())
    scen_choices = sorted(builtins)
    fpath = bookmarks_file(LAB_DIR)
    try:
        fpath_rel = str(fpath.relative_to(PROJECT_ROOT))
    except ValueError:
        fpath_rel = str(fpath)

    while True:
        marks = load_bookmarks(LAB_DIR)
        _section_header(
            console,
            "Signets scénarios",
            f"Fichier : {fpath_rel} · équivalent CLI : « python scripts/modem_lab/cli.py bookmark -h »",
        )
        ch = _select(
            console,
            questionary,
            "Action",
            [
                questionary.Choice("Afficher la liste (aperçu)", value="list"),
                questionary.Choice("Ajouter un signet", value="add"),
                questionary.Choice("Modifier un signet", value="set"),
                questionary.Choice("Supprimer un signet", value="remove"),
                questionary.Choice("Lancer un signet (cli.py)", value="run"),
                questionary.Choice("Retour au menu principal", value="back"),
            ],
        )
        if ch is None or ch == "back":
            return

        if ch == "list":
            if not marks:
                console.print(Panel("(aucun signet — « Ajouter » ou copier scenario_bookmarks.example.json)", title="Signets"))
            else:
                tbl = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
                tbl.add_column("id", style="green", no_wrap=True)
                tbl.add_column("scénario", no_wrap=True)
                tbl.add_column("description", style="dim")
                tbl.add_column("args figés", style="white")
                for bid in sorted(marks):
                    m = marks[bid]
                    args_s = " ".join(m.get("args") or [])
                    if len(args_s) > 48:
                        args_s = args_s[:45] + "…"
                    tbl.add_row(bid, m.get("scenario", ""), (m.get("description") or "")[:60], args_s)
                console.print(tbl)
            _pause(console)

        elif ch == "add":
            bid = _text_raw(questionary, "Identifiant du signet (lettre puis [a-z0-9_-])", default="").strip()
            err = validate_bookmark_id(bid, builtins)
            if err:
                console.print(f"[err]{err}[/]")
                _pause(console)
                continue
            if bid in marks:
                console.print("[err]Cet identifiant existe déjà — utiliser « Modifier ».[/]")
                _pause(console)
                continue
            scen = _select(
                console,
                questionary,
                "Scénario intégré cible",
                [questionary.Choice(s, value=s) for s in scen_choices],
                default=scen_choices[0] if scen_choices else None,
            )
            if not scen:
                continue
            desc = _text_raw(questionary, "Description (optionnel)", default="")
            args_s = _text_raw(
                questionary,
                "Arguments figés (ex: --hold-seconds 5) — laisser vide si aucun",
                default="",
            )
            try:
                stored = shlex.split(args_s, posix=False) if args_s.strip() else []
            except ValueError as e:
                console.print(f"[err]Découpage des arguments : {e}[/]")
                _pause(console)
                continue
            marks[bid] = {"scenario": scen, "args": stored, "description": desc.strip()}
            save_bookmarks(LAB_DIR, marks)
            console.print(f"[ok]Signet « {bid} » enregistré.[/]")
            _pause(console)

        elif ch == "set":
            if not marks:
                console.print("[warn]Aucun signet à modifier.[/]")
                _pause(console)
                continue
            bid = _select(
                console,
                questionary,
                "Signet à modifier",
                [questionary.Choice(f"{k}  → {marks[k].get('scenario', '')}", value=k) for k in sorted(marks)],
            )
            if not bid:
                continue
            cur = marks[bid]
            scen = _select(
                console,
                questionary,
                "Scénario intégré",
                [questionary.Choice(s, value=s) for s in scen_choices],
                default=cur.get("scenario") or scen_choices[0],
            )
            if not scen:
                continue
            desc = _text_raw(questionary, "Description", default=cur.get("description") or "")
            args_s = _text_raw(
                questionary,
                "Arguments figés (remplace l’ancienne liste)",
                default=" ".join(shlex.quote(a) for a in (cur.get("args") or [])),
            )
            try:
                stored = shlex.split(args_s, posix=False) if args_s.strip() else []
            except ValueError as e:
                console.print(f"[err]Découpage des arguments : {e}[/]")
                _pause(console)
                continue
            marks[bid] = {"scenario": scen, "args": stored, "description": desc.strip()}
            save_bookmarks(LAB_DIR, marks)
            console.print(f"[ok]Signet « {bid} » mis à jour.[/]")
            _pause(console)

        elif ch == "remove":
            if not marks:
                console.print("[warn]Aucun signet.[/]")
                _pause(console)
                continue
            bid = _select(
                console,
                questionary,
                "Signet à supprimer",
                [questionary.Choice(f"{k}", value=k) for k in sorted(marks)],
            )
            if not bid:
                continue
            if not _confirm(questionary, f"Supprimer définitivement « {bid} » ?", default=False):
                continue
            del marks[bid]
            save_bookmarks(LAB_DIR, marks)
            console.print(f"[ok]Signet « {bid} » supprimé.[/]")
            _pause(console)

        elif ch == "run":
            if not marks:
                console.print("[warn]Aucun signet — créez-en un d’abord.[/]")
                _pause(console)
                continue
            bid = _select(
                console,
                questionary,
                "Signet à lancer",
                [questionary.Choice(f"{k}  ({marks[k].get('scenario', '')})", value=k) for k in sorted(marks)],
            )
            if not bid:
                continue
            port = presets.get("port", "COM6")
            number = presets.get("default_number", "147")
            default_extra = f"--port {port} --number {number}"
            extra_s = _text_raw(
                questionary,
                "Arguments supplémentaires (ajoutés après les args figés du signet)",
                default=default_extra,
            )
            try:
                extra = shlex.split(extra_s, posix=False) if extra_s.strip() else []
            except ValueError as e:
                console.print(f"[err]Découpage : {e}[/]")
                _pause(console)
                continue
            _run_cli_target(console, bid, extra)


def menu_scenarios(console, questionary, presets: dict) -> None:
    """Menus scénarios : dispatch via ``cli.py`` (aligné sur labscenarios/README)."""
    port = presets["port"]
    number = presets["default_number"]
    delay = presets["answer_delay_ms"]
    q = questionary
    Sep = questionary.Separator

    while True:
        _section_header(console, "Scénarios modem", "USB / AT+VRX · lancement via cli.py")
        ch = _select(
            console,
            questionary,
            "Scénario à lancer",
            [
                Sep("── Basique ──"),
                q.Choice("Smoke tests AT", value="smoke"),
                q.Choice("Dialer — appel sortant simple", value="dialer"),
                q.Choice("Outgoing + clavier DTMF", value="outgoing"),
                q.Choice("Appel entrant (pont audio)", value="incoming"),
                q.Choice("DTMF keypad (ligne établie)", value="dtmf"),
                q.Choice("Répondeur entrant", value="answering"),
                q.Choice("Outbound announce (WAV sur la ligne)", value="outbound-announce"),
                Sep("── Sondes, métriques & Vosk ──"),
                q.Choice("Answer metrics probe (CSV + capture.wav)", value="answer-metrics-probe"),
                q.Choice("Answer Vosk live probe (STT temps réel + SRT)", value="answer-vosk-live-probe"),
                q.Choice("Metrics voicemail (sonde + prompt + bip + message)", value="metrics-voicemail"),
                q.Choice("Prospection outbound (greeting + Vosk + intents)", value="prospection-outbound"),
                Sep("── Autres sortants ──"),
                q.Choice("Outbound listen VAD (VRX sans WAV)", value="outbound-listen-vad"),
                q.Choice("Prompt and play (WAV préchargés / séquence)", value="prompt-and-play"),
                Sep("──"),
                q.Choice("Retour au menu principal", value="back"),
            ],
        )
        if ch is None or ch == "back":
            return

        if ch == "smoke":
            _run_cli_target(console, "smoke", ["--port", port])

        elif ch == "dialer":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            hold = _ask_text(questionary, presets, "Durée avant raccrochage (s)", "hold_seconds")
            presets["default_number"] = number
            presets["hold_seconds"] = hold
            _save_presets(presets)
            _run_cli_target(
                console,
                "dialer",
                ["--port", port, "--number", number, "--hold-seconds", hold],
            )

        elif ch == "outgoing":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            presets["default_number"] = number
            _save_presets(presets)
            _run_cli_target(console, "outgoing", ["--port", port, "--number", number])

        elif ch == "incoming":
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
            tail = ["--port", port]
            if auto:
                delay = _ask_text(questionary, presets, "Délai auto answer (ms)", "answer_delay_ms", override=delay)
                presets["answer_delay_ms"] = delay
                tail.extend(["--auto-answer", "--answer-delay-ms", delay])
            else:
                tail.append("--manual-answer")
            tail.extend(["--uplink-burst-ms", burst, "--ptt-ms", ptt_ms])
            if in_dev:
                tail.extend(["--input-device", in_dev])
            if out_dev:
                tail.extend(["--output-device", out_dev])
            if rx_only.lower().startswith("y"):
                tail.append("--rx-only")
            if ptt.lower().startswith("y"):
                tail.append("--push-to-talk")
            _save_presets(presets)
            _run_cli_target(console, "incoming", tail)

        elif ch == "dtmf":
            num_in = _text_raw(questionary, "Numéro (vide si ligne déjà établie)", default="")
            tail = ["--port", port]
            if num_in.strip():
                presets["default_number"] = num_in.strip()
                tail.extend(["--number", num_in.strip()])
            _save_presets(presets)
            _run_cli_target(console, "dtmf", tail)

        elif ch == "answering":
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
            tail = [
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
                tail.extend(["--greeting-wav", greeting])
            if vm_beep.lower().startswith("y"):
                tail.append("--beep")
            _run_cli_target(console, "answering", tail)

        elif ch == "outbound-announce":
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
            tail = [
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
                tail.append("--wait-remote-answer")
            if not prep_v:
                tail.append("--no-prepare-voice-line")
            try:
                rs = float(rec_s.replace(",", "."))
            except ValueError:
                rs = 0.0
            if rs > 0:
                tail.extend(["--record-seconds", str(rs)])
                if beep_rec:
                    tail.append("--beep-before-record")
            if quiet_h:
                tail.append("--quiet-hangup-tty")
            _save_presets(presets)
            _run_cli_target(console, "outbound-announce", tail)

        elif ch == "answer-metrics-probe":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            presets["default_number"] = number
            _save_presets(presets)
            _run_cli_target(console, "answer-metrics-probe", ["--port", port, "--number", number])

        elif ch == "answer-vosk-live-probe":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            slug = _ask_text(questionary, presets, "Slug modèle Vosk (ex. small-fr)", "vosk_model_slug")
            listen_s = _ask_text(questionary, presets, "Écoute STT max (s)", "answer_vosk_listen_sec")
            sub_off = _ask_text(
                questionary,
                presets,
                "Décalage SRT additionnel (s), après alignement sur 1re tonalité ; 0 = aucun",
                "subtitle_timeline_offset_sec",
            )
            ring_align = _ask_text(
                questionary,
                presets,
                "SRT + WAV : origine t=0 à la 1re tonalité (troncature début WAV) ? (y/n)",
                "answer_vosk_srt_origin_first_ring",
            )
            presets["default_number"] = number
            presets["vosk_model_slug"] = slug
            presets["answer_vosk_listen_sec"] = listen_s
            presets["subtitle_timeline_offset_sec"] = sub_off
            presets["answer_vosk_srt_origin_first_ring"] = ring_align
            _save_presets(presets)
            tail = [
                "--port",
                port,
                "--number",
                number,
                "--listen-sec",
                listen_s.replace(",", "."),
                "--subtitle-timeline-offset-sec",
                sub_off.replace(",", "."),
            ]
            if str(ring_align).strip().lower() in ("n", "no", "0", "false", "non"):
                tail.append("--no-srt-origin-first-ring")
            if slug.strip():
                tail.extend(["--vosk-model-slug", slug.strip()])
            _run_cli_target(console, "answer-vosk-live-probe", tail)

        elif ch == "metrics-voicemail":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            prompt_wav = _ask_text(
                questionary,
                presets,
                "WAV prompt (après détection voix)",
                "outbound_announce_wav",
                override=presets.get(
                    "outbound_announce_wav",
                    str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
                ),
            )
            presets["default_number"] = number
            presets["outbound_announce_wav"] = prompt_wav
            _save_presets(presets)
            _run_cli_target(
                console,
                "metrics-voicemail",
                ["--port", port, "--number", number, "--prompt-wav", prompt_wav],
            )

        elif ch == "prospection-outbound":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            slug = _ask_text(questionary, presets, "Slug modèle Vosk", "vosk_model_slug")
            pack_rel = (presets.get("intent_pack_out_rel") or "").strip()
            pack_path = (PROJECT_ROOT / pack_rel).resolve() if pack_rel else None
            default_greet = ""
            if pack_path and pack_path.is_dir():
                cand = pack_path / "greeting_01.wav"
                if cand.is_file():
                    default_greet = str(cand)
            if not default_greet:
                default_greet = presets.get(
                    "outbound_announce_wav",
                    str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
                )
            greeting = _text_raw(
                questionary,
                "WAV greeting (ou laisser vide pour --audio-pack-dir = pack intents)",
                default=default_greet,
            ).strip()
            try_reply = _confirm(questionary, "Activer --try-intent-reply (pack + JSON intents) ?", default=False)
            presets["default_number"] = number
            presets["vosk_model_slug"] = slug
            _save_presets(presets)
            tail = ["--port", port, "--number", number]
            if slug.strip():
                tail.extend(["--vosk-model-slug", slug.strip()])
            if greeting:
                tail.extend(["--greeting-wav", greeting])
            elif pack_path and pack_path.is_dir():
                tail.extend(["--audio-pack-dir", str(pack_path)])
            else:
                console.print("[err]Indique un WAV greeting ou un dossier pack intents valide.[/]")
                _pause(console)
                continue
            if try_reply:
                tail.append("--try-intent-reply")
                intents_rel = (presets.get("intent_pack_last_rel") or "").strip()
                if intents_rel:
                    tail.extend(["--intents-json", str((PROJECT_ROOT / intents_rel).resolve())])
                if pack_path and pack_path.is_dir() and not any(a == "--audio-pack-dir" for a in tail):
                    tail.extend(["--audio-pack-dir", str(pack_path)])
            _run_cli_target(console, "prospection-outbound", tail)

        elif ch == "outbound-listen-vad":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            listen_s = _ask_text(questionary, presets, "Écoute VAD max (s)", "outbound_vad_listen_sec")
            presets["default_number"] = number
            presets["outbound_vad_listen_sec"] = listen_s
            _save_presets(presets)
            _run_cli_target(
                console,
                "outbound-listen-vad",
                ["--port", port, "--number", number, "--listen-sec", listen_s.replace(",", ".")],
            )

        elif ch == "prompt-and-play":
            number = _ask_text(questionary, presets, "Numéro à appeler", "default_number", override=number)
            wav_path = _ask_text(
                questionary,
                presets,
                "Fichier WAV (clé « welcome »)",
                "outbound_announce_wav",
                override=presets.get(
                    "outbound_announce_wav",
                    str(LAB_DIR / "generated" / "default" / "modem_wav" / "welcome.wav"),
                ),
            )
            seq = _ask_text(questionary, presets, "Séquence de clés (CSV)", "prompt_play_sequence")
            presets["default_number"] = number
            presets["outbound_announce_wav"] = wav_path
            presets["prompt_play_sequence"] = seq
            _save_presets(presets)
            binding = f"welcome:{wav_path}"
            tail = ["--port", port, "--number", number, "--wav", binding]
            if seq.strip():
                tail.extend(["--sequence", seq.strip()])
            _run_cli_target(console, "prompt-and-play", tail)


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
                questionary.Choice("Scénarios modem (basique, sondes Vosk, prospection…)", value="scen"),
                questionary.Choice("Signets scénarios (raccourcis cli.py, JSON local)", value="bkm"),
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
        elif ch == "bkm":
            menu_scenario_bookmarks(console, questionary, presets)
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
