#!/usr/bin/env python3
"""
CLI unifiée pour lancer tous les scénarios modem_lab.

Conception
----------
- une seule commande d'entrée (`cli.py`)
- un sous-commande par scénario (`dialer`, `incoming`, `outbound-announce`, …)
- les arguments restants sont transmis tels quels au script cible
- **signets** : raccourcis nommés (fichier ``scenario_bookmarks.json``) — ``cli.py bookmark -h``

Exemple
-------
`python scripts/modem_lab/cli.py dialer -- --port COM6 --number 147`
`python scripts/modem_lab/cli.py mon-alias -- --port COM6 --number 147`

Voir aussi ``labscenarios/README.md`` (rôles des scénarios, sonde vs répondeur entrant/sortant).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parent

# Table de routage: nom public de la sous-commande -> script Python réel.
# Ordre aligné sur labscenarios/README.md (VRX/Vosk, sortant simple, entrant, avancé).
SCENARIO_MAP = {
    # VRX / métriques / Vosk
    "answer-metrics-probe": LAB_DIR / "labscenarios" / "answer_metrics_probe.py",
    "answer-vosk-live-probe": LAB_DIR / "labscenarios" / "answer_vosk_live_probe.py",
    "metrics-voicemail": LAB_DIR / "labscenarios" / "metrics_voicemail.py",
    "prospection-outbound": LAB_DIR / "labscenarios" / "prospection_outbound.py",
    # Sortant simple
    "dialer": LAB_DIR / "labscenarios" / "dialer.py",
    "outgoing": LAB_DIR / "labscenarios" / "outgoing_call.py",
    "outbound-announce": LAB_DIR / "labscenarios" / "outbound_announce.py",
    "outbound-listen-vad": LAB_DIR / "labscenarios" / "outbound_listen_vad.py",
    "outbound-pc-headset": LAB_DIR / "labscenarios" / "outbound_pc_headset.py",
    "pc-headset-direct": LAB_DIR / "labscenarios" / "pc_headset_direct.py",
    # Entrant / utilitaires
    "incoming": LAB_DIR / "labscenarios" / "incoming_call.py",
    "answering": LAB_DIR / "labscenarios" / "answering_machine.py",
    "dtmf": LAB_DIR / "labscenarios" / "dtmf_keypad.py",
    "smoke": LAB_DIR / "labscenarios" / "smoke_tests.py",
    # Avancé
    "prompt-and-play": LAB_DIR / "labscenarios" / "prompt_and_play.py",
}


def _import_bookmarks():
    from labcore.scenario_bookmarks import (
        load_bookmarks,
        merge_bookmark_and_user_args,
        resolve_run,
        save_bookmarks,
        validate_bookmark_id,
    )

    return (
        load_bookmarks,
        merge_bookmark_and_user_args,
        resolve_run,
        save_bookmarks,
        validate_bookmark_id,
    )


def _run_epilog() -> str:
    return """
Scénarios (détail : scripts/modem_lab/labscenarios/README.md) :

  VRX / métriques / Vosk
    answer-metrics-probe     Sonde VRX : métriques + capture.wav + rapport timing.
    answer-vosk-live-probe   Compose + STT Vosk live + transcript.srt en continu.
    metrics-voicemail        Sonde puis prompt WAV, bips, message (sortant).
    prospection-outbound     Sonde + greeting + STT Vosk + réponse intent optionnelle.

  Sortant simple
    dialer                   Compose, maintient la ligne, raccroche.
    outgoing                 Compose puis DTMF interactif (clavier).
    outbound-announce        Compose, attentes, lecture WAV vers la ligne.
    outbound-listen-vad      VRX + VAD sans WAV (logs parole).
    outbound-pc-headset      Compose + 1er WAV d'ouverture, puis conversation micro-casque PC.
    pc-headset-direct        Sans modem: bip d'ouverture puis conversation micro-casque locale.

  Entrant / utilitaires
    incoming                 Attente RING, décrochage, pont audio.
    answering                Répondeur entrant (greeting + enregistrement).
    dtmf                     DTMF sur ligne établie.
    smoke                    Fumée AT / modem prêt.

  Avancé
    prompt-and-play        Séquences audio / touches.

Signets : noms supplémentaires listés par « cli.py bookmark list » (fichier scenario_bookmarks.json).
"""


def build_run_parser(bookmark_ids: list[str]) -> argparse.ArgumentParser:
    choices = sorted(set(SCENARIO_MAP.keys()) | set(bookmark_ids))
    parser = argparse.ArgumentParser(
        description="CLI unifiée modem_lab (dispatch vers scripts labscenarios/*).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_run_epilog().strip(),
    )
    parser.add_argument(
        "target",
        choices=choices,
        help="Scénario intégré ou identifiant de signet.",
    )
    parser.add_argument(
        "target_args",
        nargs=argparse.REMAINDER,
        help="Arguments transmis au script cible (préfixer avec --).",
    )
    return parser


def build_run_command(target: str, target_args: list[str], bookmarks: dict) -> list[str]:
    _, merge_b, resolve_b, _, _ = _import_bookmarks()
    resolved = resolve_b(target, scenario_map=SCENARIO_MAP, bookmarks=bookmarks)
    if resolved is None:
        raise SystemExit(f"Cible inconnue ou signet cassé : {target!r}")
    script, prefix = resolved
    tail = merge_b(prefix, list(target_args))
    return [sys.executable, str(script), *tail]


def _bookmark_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Gérer les signets (raccourcis scénario + arguments figés).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  python scripts/modem_lab/cli.py bookmark list\n"
            "  python scripts/modem_lab/cli.py bookmark add --id dial-court --scenario dialer "
            "--description \"Hold 5s\" -- --hold-seconds 5\n"
            "  python scripts/modem_lab/cli.py bookmark remove --id dial-court\n"
            "  python scripts/modem_lab/cli.py dial-court -- --port COM6 --number 147\n"
            "Fichier : scripts/modem_lab/scenario_bookmarks.json — modèle : scenario_bookmarks.example.json"
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Liste les signets.")

    p_show = sub.add_parser("show", help="Affiche un signet.")
    p_show.add_argument("--id", required=True, dest="bookmark_id", help="Identifiant du signet.")

    p_rm = sub.add_parser("remove", help="Supprime un signet.")
    p_rm.add_argument("--id", required=True, dest="bookmark_id", help="Identifiant du signet.")

    scen_choices = sorted(SCENARIO_MAP.keys())

    p_add = sub.add_parser("add", help="Crée un signet (les arguments après -- sont stockés tels quels).")
    p_add.add_argument("--id", required=True, dest="bookmark_id", help="Identifiant unique.")
    p_add.add_argument(
        "--scenario",
        required=True,
        choices=scen_choices,
        help="Scénario intégré cible.",
    )
    p_add.add_argument("--description", default="", help="Texte libre (optionnel).")
    p_add.add_argument(
        "stored_args",
        nargs=argparse.REMAINDER,
        help="Arguments figés ; utiliser -- avant la première option (ex. -- --hold-seconds 5).",
    )

    p_set = sub.add_parser(
        "set",
        help="Met à jour un signet existant (remplace scénario, description et arguments figés).",
    )
    p_set.add_argument("--id", required=True, dest="bookmark_id", help="Identifiant du signet.")
    p_set.add_argument("--scenario", required=True, choices=scen_choices, help="Scénario intégré cible.")
    p_set.add_argument("--description", default="", help="Texte libre (optionnel).")
    p_set.add_argument(
        "stored_args",
        nargs=argparse.REMAINDER,
        help="Nouveaux arguments figés ; utiliser -- avant les options.",
    )

    return p


def shlex_join(parts: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(p) for p in parts)


def bookmark_main(argv: list[str]) -> int:
    load_b, _, _, save_b, validate_b = _import_bookmarks()
    ns = _bookmark_parser().parse_args(argv)
    builtins = set(SCENARIO_MAP.keys())
    marks = load_b(LAB_DIR)

    if ns.cmd == "list":
        if not marks:
            print("(aucun signet — voir « cli.py bookmark add -h »)")
            return 0
        w_id = max(len(k) for k in marks)
        w_sc = max(len(m["scenario"]) for m in marks.values())
        for bid in sorted(marks):
            m = marks[bid]
            desc = (m.get("description") or "").replace("\n", " ").strip()
            extra = " ".join(m.get("args") or [])
            if len(extra) > 56:
                extra = extra[:53] + "..."
            line = f"{bid:{w_id}}  {m['scenario']:{w_sc}}  {desc}"
            if extra:
                line += f"\n{'':{w_id}}  {'':{w_sc}}  args: {extra}"
            print(line)
        return 0

    if ns.cmd == "show":
        m = marks.get(ns.bookmark_id)
        if not m:
            print(f"Signet inconnu : {ns.bookmark_id!r}", file=sys.stderr)
            return 2
        print(f"id:          {ns.bookmark_id}")
        print(f"scenario:    {m['scenario']}")
        print(f"description: {m.get('description') or '(vide)'}")
        print(f"args:        {shlex_join(m.get('args') or [])}")
        return 0

    if ns.cmd == "remove":
        if ns.bookmark_id not in marks:
            print(f"Signet inconnu : {ns.bookmark_id!r}", file=sys.stderr)
            return 2
        del marks[ns.bookmark_id]
        save_b(LAB_DIR, marks)
        print(f"Signet supprimé : {ns.bookmark_id}")
        return 0

    if ns.cmd in ("add", "set"):
        bid = ns.bookmark_id
        err = validate_b(bid, builtins)
        if err:
            print(f"Erreur : {err}", file=sys.stderr)
            return 2
        if ns.cmd == "add" and bid in marks:
            print(f"Le signet « {bid} » existe déjà — utilisez « bookmark set » ou « bookmark remove ».", file=sys.stderr)
            return 2
        if ns.cmd == "set" and bid not in marks:
            print(f"Signet inconnu : {bid!r} — utilisez « bookmark add ».", file=sys.stderr)
            return 2
        stored = list(ns.stored_args or [])
        if stored and stored[0] == "--":
            stored = stored[1:]
        marks[bid] = {
            "scenario": ns.scenario,
            "args": stored,
            "description": (ns.description or "").strip(),
        }
        save_b(LAB_DIR, marks)
        print(f"Signet enregistré : {bid} -> {ns.scenario} {shlex_join(stored)}")
        return 0

    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        load_b, _, _, _, _ = _import_bookmarks()
        marks = load_b(LAB_DIR)
        build_run_parser(sorted(marks.keys())).print_help()
        return 0
    if argv[0] == "bookmark":
        return bookmark_main(argv[1:])

    load_b, _, _, _, _ = _import_bookmarks()
    marks = load_b(LAB_DIR)
    ns = build_run_parser(sorted(marks.keys())).parse_args(argv)
    cmd = build_run_command(ns.target, list(ns.target_args), marks)
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        # Évite la traceback du wrapper CLI quand le scénario enfant est interrompu.
        return 130


if __name__ == "__main__":
    if str(LAB_DIR) not in sys.path:
        sys.path.insert(0, str(LAB_DIR))
    raise SystemExit(main())
