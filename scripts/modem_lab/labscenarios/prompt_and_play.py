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
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from loguru import logger

from labcore.bootstrap import add_modem_args, build_modem, setup_logging
from labcore.call_control import CallController, HangupStyle
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


def parse_args() -> argparse.Namespace:
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
        default=True,
        help="Composition aveugle ATDT...; (défaut: oui).",
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
    return p.parse_args()


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


async def _interactive_play(bank: WavBank) -> None:
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
            ok = await bank.play(cmd, prefer_already_in_voice=True)
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

        # seq contient l'ordre de lecture demandé (vide => mode interactif)
        seq = _parse_sequence(args.sequence) if args.sequence else []
        if seq:
            ok = await _play_keys(
                bank,
                seq,
                prefer_already_in_voice=True,
                inter_key_delay_sec=max(0.0, float(args.inter_key_delay_sec)),
            )
            if not ok:
                return 5
        else:
            await _interactive_play(bank)
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

