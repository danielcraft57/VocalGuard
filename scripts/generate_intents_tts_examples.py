#!/usr/bin/env python3
"""
Genere des exemples audio a partir des intents IVR avec edge-tts.
Menu pour afficher les voix disponibles et en choisir une, puis generation
des fichiers MP3 (ou WAV 8 kHz si pydub/ffmpeg dispo) pour chaque intent.
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# Racine du projet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.voice.intents_loader import load_intents_ivr


async def list_voices(locale_filter: Optional[str] = None) -> List[dict]:
    """
    Retourne la liste des voix edge-tts.
    Si locale_filter est renseigne (ex. "fr"), ne garde que ces voix.
    """
    try:
        import edge_tts
    except ImportError:
        print("edge-tts n'est pas installe. Installez avec: pip install edge-tts")
        return []
    voices = await edge_tts.list_voices()
    if locale_filter:
        voices = [v for v in voices if v.get("Locale", "").lower().startswith(locale_filter.lower())]
    return sorted(voices, key=lambda v: (v.get("Locale", ""), v.get("ShortName", "")))


def display_voices(voices: List[dict], title: str = "Voix disponibles") -> None:
    """Affiche les voix en tableau numerote (index, ShortName, Gender, Locale)."""
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


async def generate_for_intents(voice_name: str, out_dir: Path, as_wav_8k: bool = True):
    """
    Genere un fichier audio par intent (response) avec edge-tts.
    out_dir: dossier de sortie (ex. ivr_wav ou tts_examples).
    as_wav_8k: si True et pydub dispo, convertit en WAV 8 kHz mono (telephone).
    """
    try:
        import edge_tts
    except ImportError:
        print("edge-tts n'est pas installe. pip install edge-tts")
        return 0
    intents, default_intent, exit_intent = load_intents_ivr(base_path=PROJECT_ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)
    to_generate = []
    for item in intents:
        to_generate.append((item.get("filename", "ivr_unknown.wav"), item.get("response", "")))
    to_generate.append((default_intent.get("filename", "ivr_incompris.wav"), default_intent.get("response", "")))
    to_generate.append((exit_intent.get("filename", "ivr_fin.wav"), exit_intent.get("response", "")))
    use_mp3 = not as_wav_8k
    try:
        from pydub import AudioSegment
        has_pydub = True
    except ImportError:
        has_pydub = False
        use_mp3 = True
    generated = 0
    for filename, text in to_generate:
        if not text:
            continue
        base = Path(filename).stem
        ext = "mp3"
        out_path = out_dir / f"{base}.{ext}"
        communicate = edge_tts.Communicate(text, voice_name)
        await communicate.save(str(out_path))
        generated += 1
        if use_mp3:
            print(f"  {out_path}")
        else:
            try:
                audio = AudioSegment.from_file(str(out_path))
                audio = audio.set_frame_rate(8000).set_channels(1)
                wav_path = out_dir / f"{base}.wav"
                audio.export(str(wav_path), format="wav")
                out_path.unlink(missing_ok=True)
                out_path = wav_path
                print(f"  {out_path}")
            except Exception as e:
                print(f"  {out_path} (conversion WAV ignoree: {e})")
    return generated


def input_voice_index(voices: List[dict]) -> Optional[str]:
    """Demande a l'utilisateur de choisir une voix par numero. Retourne ShortName ou None."""
    if not voices:
        return None
    while True:
        raw = input("Numero de la voix (ou Entree pour annuler): ").strip()
        if not raw:
            return None
        try:
            idx = int(raw)
            if 0 <= idx < len(voices):
                return voices[idx].get("ShortName")
        except ValueError:
            pass
        print("Numero invalide.")


async def run_menu():
    """Boucle menu: afficher voix (toutes / FR), choisir voix, generer exemples."""
    voices_all = await list_voices(locale_filter=None)
    voices_fr = await list_voices(locale_filter="fr")
    chosen_voice = None
    out_dir = PROJECT_ROOT / "ivr_wav"
    while True:
        print("\n--- Menu TTS exemples (intents IVR) ---")
        print("  1. Afficher toutes les voix")
        print("  2. Afficher les voix francaises uniquement")
        print("  3. Choisir une voix pour la generation")
        print("  4. Generer les exemples avec la voix choisie")
        print("  5. Quitter")
        if chosen_voice:
            print(f"  [Voix actuelle: {chosen_voice}]")
        print()
        choice = input("Choix (1-5): ").strip()
        if choice == "1":
            display_voices(voices_all, "Toutes les voix")
        elif choice == "2":
            display_voices(voices_fr, "Voix francaises")
        elif choice == "3":
            display_voices(voices_fr, "Voix francaises - choisir un numero")
            if voices_fr:
                chosen_voice = input_voice_index(voices_fr)
                if chosen_voice:
                    print(f"Voix selectionnee: {chosen_voice}")
            else:
                print("Afficher d'abord les voix (option 1 ou 2).")
        elif choice == "4":
            if not chosen_voice:
                print("Choisissez d'abord une voix (option 3).")
                continue
            print(f"Generation des exemples dans {out_dir} avec la voix {chosen_voice}...")
            n = await generate_for_intents(chosen_voice, out_dir, as_wav_8k=True)
            print(f"Termine: {n} fichier(s) genere(s).")
        elif choice == "5":
            print("Au revoir.")
            break
        else:
            print("Choix invalide.")


def main():
    print("Script de generation d'exemples TTS a partir des intents IVR (edge-tts).")
    print("Fichier d'intents: config/intents_ivr.yaml ou config/intents_ivr.example.yaml")
    asyncio.run(run_menu())


if __name__ == "__main__":
    main()
