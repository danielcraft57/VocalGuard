#!/usr/bin/env python3
"""
Test simple de lecture audio avec différentes méthodes
"""

import asyncio
import sys
from pathlib import Path

async def test_winsound(audio_file: Path):
    """Test avec winsound"""
    try:
        import winsound
        import wave
        
        print(f"Test winsound avec: {audio_file}")
        
        # Calculer la durée
        with wave.open(str(audio_file), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration = frames / float(rate)
            print(f"Durée: {duration:.2f}s")
        
        print("Lecture en cours...")
        winsound.PlaySound(str(audio_file), winsound.SND_FILENAME | winsound.SND_ASYNC)
        await asyncio.sleep(duration + 0.5)
        print("[OK] winsound fonctionne!")
        return True
    except Exception as e:
        print(f"[ERREUR] Erreur winsound: {e}")
        return False

async def main():
    cache_dir = Path.home() / '.vocalguard' / 'audio_cache'
    wav_files = list(cache_dir.glob('*.wav'))
    
    if not wav_files:
        print("[ERREUR] Aucun fichier WAV trouve dans le cache")
        return
    
    test_file = wav_files[0]
    print(f"Fichier de test: {test_file}")
    print(f"Taille: {test_file.stat().st_size} bytes")
    print()
    
    success = await test_winsound(test_file)
    
    if success:
        print("\n[OK] winsound fonctionne correctement!")
    else:
        print("\n[ERREUR] winsound ne fonctionne pas")
        print("Astuce: Essayez: pip install pygame")

if __name__ == "__main__":
    asyncio.run(main())
