#!/usr/bin/env python3
"""
Scénario "prompt and play" : compose un appel puis joue des messages WAV préchargés.

Objectif principal
------------------
Réduire la latence entre "je veux jouer ce prompt" et l'envoi réel sur la ligne PSTN :
les WAV sont chargés en mémoire (PCM u8) avant la composition, puis joués par clé.

Modes disponibles
-----------------
1) Séquence prédéfinie (``--sequence welcome,beep,outro``)
2) Mode interactif (pas de ``--sequence``) : saisie clavier de la clé à jouer.

Pourquoi ce scénario est utile
------------------------------
- évite le coût I/O disque au moment critique AT+VTX
- facilite les tests terrain (enchaînements reproductibles)
- permet de piloter rapidement plusieurs prompts métiers (accueil, menu, erreur, fin)

Préconfiguration (--profile)
---------------------------
- ``default`` : comportement historique (flags explicites requis pour l'attente voix stricte).
- ``mobile-calibrated`` : bundle calibré ringback long / mobile (voir ``--help``), composition
  en mode ``prepare_voice_for_blind_dial`` par défaut (pas off-hook avant ``ATD``).
- Fichier JSON optionnel ``modem_lab/prompt_and_play_presets.json`` : mêmes clés que les
  attributs argparse (snake_case), pour ajouter ou surcharger des profils nommés.

Attente décroché / métriques
----------------------------
La phase ``--wait-answer-or-voice-sec > 0`` utilise ``labcore.answer_wait_common`` (même
code que ``answer_metrics_probe``) : VRX, ``already_in_voice_mode`` aligné sur la préparation
(``False`` sauf ``--prepare-offhook``), extension de timeout si ``--capture-window-sec``,
optionnellement CSV + WAV + rapport avec ``--dated-answer-capture``.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from loguru import logger

# Permet d'executer ce script directement depuis la racine du depot
# (python scripts/modem_lab/labscenarios/prompt_and_play.py)
# en rendant importables les packages freres `labcore` et `labscenarios`.
_MODEM_LAB_ROOT = Path(__file__).resolve().parents[1]
if str(_MODEM_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODEM_LAB_ROOT))

from labcore.answer_wait_common import (
    AnswerWaitConfigError,
    effective_vrx_timeout,
    run_answer_wait_phase,
)
from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.call_control import CallController, HangupStyle
from labcore.call_watch import wait_remote_hangup
from labcore.line_audio_player import LineAudioPlayer
from labcore.wav_bank import WavBank


def _parse_wav_binding(raw: str) -> tuple[str, Path]:
    """
    Convertit ``CLE:CHEMIN`` en tuple (clé, Path).

    Exemple : ``welcome:assets/welcome.wav``.
    """
    if ":" not in raw:
        raise ValueError("format attendu: cle:chemin.wav")
    key, path = raw.split(":", 1)
    key = key.strip()
    path = path.strip()
    if not key:
        raise ValueError("cle vide")
    if not path:
        raise ValueError("chemin vide")
    return key, Path(path)


def _parse_sequence(raw: str) -> list[str]:
    """Transforme une liste CSV de clés en tableau nettoyé (sans entrées vides)."""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _argv_sets_dest(argv: list[str], *flag_names: str) -> bool:
    """True si la ligne de commande fixe explicitement un de ces drapeaux (ou forme --flag=val)."""
    for tok in argv:
        for name in flag_names:
            if tok == name or tok.startswith(name + "="):
                return True
    return False


# Drapeaux CLI associés aux attributs argparse (dest) que les profils peuvent modifier.
_PROFILE_DEST_FLAGS: dict[str, tuple[str, ...]] = {
    "wait_answer_or_voice_sec": ("--wait-answer-or-voice-sec",),
    "answer_on_voice_activity": ("--answer-on-voice-activity", "--no-answer-on-voice-activity"),
    "answer_on_energy_fallback": ("--answer-on-energy-fallback", "--no-answer-on-energy-fallback"),
    "wait_hangup_sec": ("--wait-hangup-sec",),
    "vad_threshold": ("--vad-threshold",),
    "vad_min_speech_ms": ("--vad-min-speech-ms",),
    "vad_hangover_ms": ("--vad-hangover-ms",),
    "min_voice_trigger_sec": ("--min-voice-trigger-sec",),
    "energy_score_min": ("--energy-score-min",),
    "energy_jitter_min": ("--energy-jitter-min",),
    "energy_score_span_min": ("--energy-score-span-min",),
    "energy_jitter_span_min": ("--energy-jitter-span-min",),
    "tone_reject": ("--tone-reject", "--no-tone-reject"),
    "tone_reject_zcr_min": ("--tone-reject-zcr-min",),
    "tone_reject_zcr_max": ("--tone-reject-zcr-max",),
    "tone_reject_periodicity_max": ("--tone-reject-periodicity-max",),
    "prepare_offhook": ("--prepare-offhook",),
}

# Profil calibré (mobile, ringback long ~9 s avant parole utile) — voir answer_metrics_probe / rapport WAV.
_MOBILE_CALIBRATED: dict[str, Any] = {
    "wait_answer_or_voice_sec": 45.0,
    "answer_on_voice_activity": True,
    "answer_on_energy_fallback": True,
    "min_voice_trigger_sec": 9.0,
    "energy_score_min": 35.0,
    "energy_jitter_min": 10.0,
    "energy_score_span_min": 8.0,
    "energy_jitter_span_min": 3.0,
    "tone_reject": True,
    "tone_reject_zcr_min": 0.04,
    "tone_reject_zcr_max": 0.30,
    "tone_reject_periodicity_max": 0.88,
    "vad_threshold": 22.0,
    "vad_min_speech_ms": 700.0,
    "vad_hangover_ms": 500.0,
    # False: +VLS=1 avant ATD fait souvent ERROR (Conexant/USR) ; le scénario passe alors par
    # prepare_voice_for_blind_dial() comme answer_metrics_probe. Ajouter --prepare-offhook si
    # votre firmware accepte la composition déjà décroché.
    "prepare_offhook": False,
    "wait_hangup_sec": 15.0,
}

_BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
    "mobile-calibrated": dict(_MOBILE_CALIBRATED),
}


def _load_prompt_and_play_presets_file() -> dict[str, dict[str, Any]]:
    """
    Charge ``modem_lab/prompt_and_play_presets.json`` si présent.

    Format: objet JSON dont chaque clé est un nom de profil et la valeur un objet
    ``dest_argparse`` -> valeur (mêmes noms que les attributs du Namespace).
    Les profils du fichier remplacent ou complètent les profils intégrés pour un même nom.
    """
    path = _MODEM_LAB_ROOT / "prompt_and_play_presets.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Lecture presets prompt_and_play ignorée ({}): {}", path, e)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, body in raw.items():
        if name == "default":
            logger.warning("Profil 'default' dans prompt_and_play_presets.json ignoré (réservé).")
            continue
        if isinstance(name, str) and isinstance(body, dict):
            out[name] = dict(body)
    return out


def prompt_and_play_profiles() -> dict[str, Mapping[str, Any]]:
    """Profils intégrés fusionnés avec ``prompt_and_play_presets.json`` (le fichier l'emporte sur le nom)."""
    return {**_BUILTIN_PROFILES, **_load_prompt_and_play_presets_file()}


def apply_prompt_and_play_profile(ns: argparse.Namespace, profile_name: str, argv: list[str]) -> None:
    """
    Applique un profil au Namespace sans écraser les paramètres déjà fixés explicitement sur argv.
    """
    if profile_name == "default":
        return
    profiles = prompt_and_play_profiles()
    body = profiles.get(profile_name)
    if not body:
        logger.warning("Profil prompt_and_play inconnu: {}", profile_name)
        return
    for dest, val in body.items():
        flags = _PROFILE_DEST_FLAGS.get(dest)
        if flags is None:
            logger.warning("Clé de profil ignorée (dest inconnu): {}", dest)
            continue
        if _argv_sets_dest(argv, *flags):
            continue
        setattr(ns, dest, val)


def parse_args() -> argparse.Namespace:
    profiles = prompt_and_play_profiles()
    p = argparse.ArgumentParser(
        description="Compose puis joue des WAV préchargés par clé (mode séquence ou interactif)."
    )
    add_modem_args(p, need_number=True)
    p.add_argument(
        "--wav",
        action="append",
        default=[],
        metavar="CLE:CHEMIN",
        help="Ajoute un WAV préchargé (répéter l'option). Ex: --wav welcome:assets/welcome.wav",
    )
    p.add_argument(
        "--sequence",
        default="",
        help="Séquence de clés séparées par des virgules (ex: welcome,beep,goodbye).",
    )
    p.add_argument(
        "--inter-key-delay-sec",
        type=float,
        default=0.12,
        help="Pause entre deux messages de la séquence.",
    )
    p.add_argument(
        "--voice-blind-dial",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Composition aveugle ATDT...; (défaut: non, pour mieux attendre le vrai décroché).",
    )
    p.add_argument(
        "--prepare-offhook",
        action="store_true",
        help="Préparation voix +VLS=1 avant composition (sinon codec seul).",
    )
    p.add_argument(
        "--hangup-style",
        choices=("turbo", "simple"),
        default="turbo",
        help="Méthode de raccrochage en fin de scénario.",
    )
    p.add_argument(
        "--wait-answer-or-voice-sec",
        type=float,
        default=0.0,
        help="Si > 0, attend d'abord un indice de décroché ou 1ère activité voix avant lecture.",
    )
    p.add_argument(
        "--answer-on-voice-activity",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Autorise la voix/VAD comme déclencheur de décroché (défaut: non, évite les faux positifs ringback).",
    )
    p.add_argument(
        "--answer-on-energy-fallback",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Active le fallback énergie brute (utile répondeur auto, plus risqué sur mobile/ringback).",
    )
    p.add_argument(
        "--wait-hangup-sec",
        type=float,
        default=0.0,
        help="Si > 0, après lecture, attend un marqueur de raccrochage distant.",
    )
    p.add_argument(
        "--vad-threshold",
        type=float,
        default=26.0,
        help="Seuil VAD pour détecter la parole distante (plus élevé = moins sensible).",
    )
    p.add_argument(
        "--vad-min-speech-ms",
        type=float,
        default=420.0,
        help="Durée minimale de parole continue pour valider un décroché par voix.",
    )
    p.add_argument(
        "--vad-hangover-ms",
        type=float,
        default=450.0,
        help="Temps de maintien VAD après parole (lissage anti-coupures).",
    )
    p.add_argument(
        "--min-voice-trigger-sec",
        type=float,
        default=-1.0,
        help="Délai minimal avant d'autoriser un déclenchement par voix (anti faux positifs ringback).",
    )
    p.add_argument("--energy-score-min", type=float, default=24.0, help="Seuil brut minimum raw_score.")
    p.add_argument("--energy-jitter-min", type=float, default=8.0, help="Seuil brut minimum raw_jitter.")
    p.add_argument(
        "--energy-score-span-min",
        type=float,
        default=6.0,
        help="Variation minimale score_span pour valider le fallback énergie.",
    )
    p.add_argument(
        "--energy-jitter-span-min",
        type=float,
        default=2.5,
        help="Variation minimale jitter_span pour valider le fallback énergie.",
    )
    p.add_argument(
        "--tone-reject",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Active le rejet tonalité via ZCR+périodicité (anti-ringback).",
    )
    p.add_argument("--tone-reject-zcr-min", type=float, default=0.03, help="Borne basse ZCR pour voix.")
    p.add_argument("--tone-reject-zcr-max", type=float, default=0.30, help="Borne haute ZCR pour voix.")
    p.add_argument(
        "--tone-reject-periodicity-max",
        type=float,
        default=0.90,
        help="Périodicité max acceptée (au-delà: signal trop tonal).",
    )
    p.add_argument(
        "--post-answer-observe-sec",
        type=float,
        default=0.0,
        help="Poursuite capture métriques/WAV après le 1er décroché/voix (comme answer-metrics-probe).",
    )
    p.add_argument(
        "--capture-delay-sec",
        type=float,
        default=0.0,
        help="Ne collecte métriques/WAV qu'après ce délai depuis l'ouverture VRX.",
    )
    p.add_argument(
        "--capture-window-sec",
        type=float,
        default=0.0,
        help="Durée max de collecte après le délai (0 = jusqu'à la fin du timeout).",
    )
    p.add_argument(
        "--dated-answer-capture",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Crée generated/prompt_and_play/<ts>/ avec metrics.csv, capture.wav, report (même pipeline que la sonde).",
    )
    p.add_argument(
        "--answer-metrics-thread",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Écriture CSV métriques via thread (recommandé si capture activée).",
    )
    p.add_argument("--answer-metrics-flush-sec", type=float, default=0.5)
    p.add_argument(
        "--answer-record-wav-mode",
        choices=("inline", "thread"),
        default="inline",
        help="inline: même VRX que les métriques (défaut).",
    )
    p.add_argument(
        "--answer-auto-report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Génère report.json/txt si un WAV de capture existe.",
    )
    p.add_argument("--answer-report-frame-ms", type=float, default=80.0)
    p.add_argument("--answer-report-hop-ms", type=float, default=40.0)
    p.add_argument(
        "--allow-play-without-answer",
        action="store_true",
        help="Autorise la lecture même si --wait-answer-or-voice-sec expire sans décroché/voix.",
    )
    p.add_argument(
        "--profile",
        choices=["default", *sorted(profiles.keys())],
        default="default",
        metavar="NAME",
        help=(
            "Pré-réglages détection décroché/voix. "
            "'mobile-calibrated': ~45 s, VAD + fallback énergie, tone-reject, min voix ~9 s, "
            "seuils énergie/VAD resserrés, attente raccrochage 15 s, sans --prepare-offhook "
            "(évite ATD→ERROR après +VLS=1 sur beaucoup de modems). "
            "Fichier optionnel: modem_lab/prompt_and_play_presets.json. "
            "Une option explicite sur la ligne de commande prime sur la valeur du profil."
        ),
    )
    args = p.parse_args()
    apply_prompt_and_play_profile(args, args.profile, sys.argv[1:])
    return args


async def _play_keys(
    bank: WavBank,
    keys: list[str],
    *,
    prefer_already_in_voice: bool,
    inter_key_delay_sec: float,
) -> bool:
    """
    Joue une liste de clés dans l'ordre.

    Retourne False dès qu'une lecture échoue pour éviter de poursuivre une campagne
    dans un état incohérent (ex. prompt manquant ou refus modem).
    """
    for idx, key in enumerate(keys, start=1):
        logger.info("Lecture [{}/{}]: {}", idx, len(keys), key)
        ok = await bank.play(key, prefer_already_in_voice=prefer_already_in_voice)
        if not ok:
            logger.warning("Lecture échouée pour '{}'", key)
            return False
        if idx < len(keys) and inter_key_delay_sec > 0:
            await asyncio.sleep(inter_key_delay_sec)
    return True


async def _interactive_play(bank: WavBank, *, prefer_already_in_voice: bool) -> None:
    """Boucle interactive de sélection de clés (``q`` pour sortir)."""
    print("Clés disponibles:", ", ".join(sorted(bank.keys())), flush=True)
    print("Saisir une clé pour jouer, 'q' pour quitter.", flush=True)
    while True:
        cmd = (await asyncio.to_thread(input, "play> ")).strip()
        if not cmd:
            continue
        if cmd.lower() in {"q", "quit", "exit"}:
            break
        try:
            ok = await bank.play(cmd, prefer_already_in_voice=prefer_already_in_voice)
            print(f"{cmd}: {'OK' if ok else 'KO'}", flush=True)
        except KeyError:
            print(f"Clé inconnue: {cmd}", flush=True)


async def run() -> int:
    """
    Exécute le scénario de bout en bout.

    Codes de retour:
    - 0 : succès / interruption volontaire
    - 1 : init modem KO
    - 2 : arguments WAV invalides
    - 3 : préparation voix KO
    - 4 : composition KO
    - 5 : échec de lecture dans la séquence
    - 6 : pas de décroché/voix avant lecture (mode strict)
    - 7 : options capture/métriques incompatibles (voir answer-metrics-probe)
    """
    args = parse_args()
    if not args.wav:
        logger.error("Aucun WAV déclaré. Utiliser au moins une option --wav cle:chemin.wav")
        return 2

    # bindings = map clé métier -> chemin wav local
    bindings: list[tuple[str, Path]] = []
    try:
        for raw in args.wav:
            bindings.append(_parse_wav_binding(raw))
    except ValueError as e:
        logger.error("Argument --wav invalide: {}", e)
        return 2

    modem = build_modem(args)
    ctl = CallController(modem)
    player = LineAudioPlayer(modem)
    bank = WavBank(player)

    try:
        if not await modem.initialize():
            logger.error("Echec initialisation modem")
            return 1

        for key, path in bindings:
            item = bank.preload(key, path)
            logger.info("Préchargé '{}' -> {} ({} octets)", key, item.source_path, len(item.pcm_u8))

        if args.prepare_offhook:
            ok_prep = await ctl.prepare_voice_off_hook()
        else:
            ok_prep = await ctl.prepare_voice_for_blind_dial()
        if not ok_prep:
            logger.error("Echec préparation voix avant composition")
            return 3

        ok_dial, raw = await ctl.dial(args.number, blind=bool(args.voice_blind_dial))
        logger.info("Dial {} -> ok={} raw={}", args.number, ok_dial, raw or "(vide)")
        if not ok_dial:
            return 4
        if bool(args.voice_blind_dial) and float(args.wait_answer_or_voice_sec) > 0 and not bool(args.answer_on_voice_activity):
            logger.warning(
                "Mode blind + attente stricte: détection décroché potentiellement limitée selon modem (DCD non exploitable)."
            )

        # Compatibilité backend: sur les versions legacy, il faut repasser par la séquence
        # complète (FCLASS/VLS) pour chaque lecture sinon l'audio peut rester muet.
        try:
            sig = inspect.signature(modem.play_wav_via_serial)
            prefer_already_in_voice = "pcm_u8" in sig.parameters
        except (TypeError, ValueError):
            prefer_already_in_voice = False

        if float(args.wait_answer_or_voice_sec) > 0:
            # Si non fourni: profil mobile prudent quand fallback énergie désactivé.
            min_voice_trigger_sec = float(args.min_voice_trigger_sec)
            if min_voice_trigger_sec < 0.0:
                min_voice_trigger_sec = 10.0 if (
                    bool(args.answer_on_voice_activity) and not bool(args.answer_on_energy_fallback)
                ) else 0.0

            metrics_out: Path | None = None
            record_wav_out: Path | None = None
            record_wav_from_start = False
            if bool(args.dated_answer_capture):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                cap_dir = Path("scripts/modem_lab/generated/prompt_and_play") / ts
                cap_dir.mkdir(parents=True, exist_ok=True)
                metrics_out = cap_dir / "metrics.csv"
                record_wav_out = cap_dir / "capture.wav"
                record_wav_from_start = True
                logger.info("Dossier capture (pipeline sonde): {}", cap_dir)

            eff_wait, cap_delay, cap_win = effective_vrx_timeout(
                float(args.wait_answer_or_voice_sec),
                float(args.capture_delay_sec),
                float(args.capture_window_sec),
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
                    min_voice_trigger_sec=min_voice_trigger_sec,
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
                    already_in_voice_mode=bool(args.prepare_offhook),
                    record_wav_from_start=record_wav_from_start,
                    record_wav_mode=str(args.answer_record_wav_mode),
                    record_wav_out=record_wav_out,
                    record_wav_sec=-1.0,
                    metrics_out=metrics_out,
                    metrics_thread=bool(args.answer_metrics_thread),
                    metrics_flush_sec=float(args.answer_metrics_flush_sec),
                    auto_report=bool(args.answer_auto_report),
                    report_frame_ms=float(args.answer_report_frame_ms),
                    report_hop_ms=float(args.answer_report_hop_ms),
                    report_session_extra={"scenario": "prompt_and_play"},
                )
            except AnswerWaitConfigError as e:
                logger.error("{}", e)
                return 7
            logger.info("Attente décroché/voix -> ready={} reason={}", ready, why)
            if not ready:
                if args.allow_play_without_answer:
                    logger.warning(
                        "Pas de décroché/voix détecté avant lecture (reason={}) — poursuite autorisée",
                        why,
                    )
                else:
                    logger.warning(
                        "Pas de décroché/voix détecté avant lecture (reason={}) — arrêt (mode strict)",
                        why,
                    )
                    return 6

        # seq contient l'ordre de lecture demandé (vide => mode interactif)
        seq = _parse_sequence(args.sequence) if args.sequence else []
        if seq:
            ok = await _play_keys(
                bank,
                seq,
                prefer_already_in_voice=prefer_already_in_voice,
                inter_key_delay_sec=max(0.0, float(args.inter_key_delay_sec)),
            )
            if not ok:
                return 5
        else:
            await _interactive_play(
                bank,
                prefer_already_in_voice=prefer_already_in_voice,
            )

        if float(args.wait_hangup_sec) > 0:
            hup, why = await wait_remote_hangup(
                modem,
                timeout_sec=float(args.wait_hangup_sec),
                already_in_voice_mode=prefer_already_in_voice,
            )
            logger.info("Attente raccrochage distant -> detected={} reason={}", hup, why)
        return 0
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.warning("Interruption utilisateur")
        return 0
    finally:
        try:
            style = HangupStyle.TURBO if args.hangup_style == "turbo" else HangupStyle.SIMPLE_ATH
            await ctl.hangup(style)
        except Exception:
            pass
        modem.close()


if __name__ == "__main__":
    setup_logging("prompt_and_play")
    raise SystemExit(asyncio.run(run()))

