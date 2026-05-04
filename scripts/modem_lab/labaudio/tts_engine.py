#!/usr/bin/env python3
"""
Copie locale du menu TTS edge-tts utilise dans le projet.
But: lister les voix, choisir une voix FR, puis generer des fichiers audio.
"""

import asyncio
from pathlib import Path
from typing import List, Optional

import sys
from loguru import logger
from labcore.line_audio_player import preview_wav_on_host

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))


async def list_voices(locale_filter: Optional[str] = None) -> List[dict]:
    try:
        import edge_tts
    except ImportError:
        print("edge-tts non installe. Installez avec: pip install edge-tts")
        return []
    voices = await edge_tts.list_voices()
    if locale_filter:
        voices = [v for v in voices if v.get("Locale", "").lower().startswith(locale_filter.lower())]
    return sorted(voices, key=lambda v: (v.get("Locale", ""), v.get("ShortName", "")))


def display_voices(voices: List[dict], title: str = "Voix disponibles") -> None:
    if not voices:
        print("Aucune voix trouvee.")
        return
    print(f"\n--- {title} ({len(voices)} voix) ---")
    print(f"{'#':>4}  {'ShortName':<28}  {'Gender':<8}  Locale")
    print("-" * 60)
    for i, v in enumerate(voices):
        short = (v.get("ShortName") or "")[:28]
        gender = (v.get("Gender") or "")[:8]
        locale = v.get("Locale") or ""
        print(f"{i:>4}  {short:<28}  {gender:<8}  {locale}")
    print()


def input_voice_index(voices: List[dict]) -> Optional[str]:
    if not voices:
        return None
    while True:
        raw = input("Numero de la voix (Entree pour annuler): ").strip()
        if not raw:
            return None
        try:
            idx = int(raw)
            if 0 <= idx < len(voices):
                return voices[idx].get("ShortName")
        except ValueError:
            pass
        print("Numero invalide.")


async def generate_sample(voice_name: str, out_path: Path) -> Optional[Path]:
    import edge_tts

    logger.info("Generation sample TTS avec voix {}", voice_name)
    text = (
        "Bonjour Loic. "
        "Ici VocalGuard, version test avec une voix IA plus naturelle. "
        "Le but est simple: verifier si le timbre est clair, le rythme fluide, "
        "et l'articulation propre sur chaque mot. "
        "Si le rendu te plait, on peut ensuite generer tout le pack audio avec cette meme voix."
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    comm = edge_tts.Communicate(
        text,
        voice_name,
        rate="+3%",
        pitch="+2Hz",
    )
    await comm.save(str(out_path))
    logger.info("Sample TTS genere: {}", out_path)
    print(f"Fichier genere: {out_path}")
    wav_path = out_path.with_suffix(".wav")
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.warning("pydub non installe: conversion WAV impossible")
        print("pydub non installe: lecture interne indisponible (pip install pydub).")
        return None
    try:
        audio = AudioSegment.from_file(str(out_path))
        audio.set_channels(1).set_frame_rate(16000).set_sample_width(2).export(str(wav_path), format="wav")
        logger.info("Sample WAV genere: {}", wav_path)
        return wav_path
    except Exception as e:
        logger.warning("Conversion MP3->WAV impossible: {}", e)
        print("Conversion en WAV impossible, lecture interne annulee.")
        return None


async def play_sample_on_host(sample_wav_path: Optional[Path]) -> bool:
    """Lit directement le sample sur la sortie audio locale (sans lecteur externe)."""
    if sample_wav_path is None or not sample_wav_path.is_file():
        logger.warning("Lecture interne impossible, sample WAV absent")
        return False
    ok = await preview_wav_on_host(sample_wav_path)
    if ok:
        print("Lecture interne terminee.")
    else:
        print("Lecture interne impossible (verifiez sounddevice/pyaudio).")
    return ok


async def run(selection_file: Optional[Path] = None, initial_voice: Optional[str] = None) -> None:
    logger.info("Demarrage menu TTS")
    voices_all = await list_voices()
    voices_fr = await list_voices("fr")
    logger.debug("Voix chargees: total={}, fr={}", len(voices_all), len(voices_fr))
    chosen_voice = initial_voice
    out_file = PROJECT_ROOT / "scripts" / "modem_lab" / "generated" / "tts_sample.mp3"

    while True:
        print("\n--- Menu TTS (copie) ---")
        print("1. Afficher toutes les voix")
        print("2. Afficher les voix francaises")
        print("3. Choisir une voix (genere et lit un sample)")
        print("4. Generer un sample MP3 puis lire")
        print("5. Quitter")
        if chosen_voice:
            print(f"[Voix actuelle: {chosen_voice}]")

        choice = input("Choix (1-5): ").strip()
        if choice == "1":
            display_voices(voices_all, "Toutes les voix")
        elif choice == "2":
            display_voices(voices_fr, "Voix francaises")
        elif choice == "3":
            display_voices(voices_fr, "Voix francaises - choisir")
            chosen_voice = input_voice_index(voices_fr)
            if chosen_voice:
                print(f"Voix selectionnee: {chosen_voice}")
                logger.info("Voix selectionnee: {}", chosen_voice)
                if selection_file is not None:
                    selection_file.parent.mkdir(parents=True, exist_ok=True)
                    selection_file.write_text(chosen_voice, encoding="utf-8")
                    logger.debug("Voix sauvegardee dans {}", selection_file)
                sample_wav = await generate_sample(chosen_voice, out_file)
                await play_sample_on_host(sample_wav)
        elif choice == "4":
            if not chosen_voice:
                print("Choisissez d'abord une voix.")
                continue
            sample_wav = await generate_sample(chosen_voice, out_file)
            await play_sample_on_host(sample_wav)
        elif choice == "5":
            return
        else:
            print("Choix invalide.")

